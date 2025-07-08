from pydantic import BaseModel, Field
from pydantic_ai import Agent
from joblib import Memory
import pydantic_ai
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
import os

from ontoeval.models import PRBenchmark

MAX_ISSUE_TEXT_LENGTH = 80_000

memory = Memory('.self-improver-memory', verbose=0)

IMPROVER_SYSTEM_PROMPT_HEADER = """
Your job is to suggest changes to your own documentation to improve your accuracy on tasks.

You will be shown a task, together with the changes proposed by an AI and the changes that were made by
a human ontology expert. You will also be shown the instructions provided to the AI to assist it in completing the task.

The assumption is that the human ontology expert gave both the biologically correct set of changes, and the set of changes
that best conform to ontology best practices. The AI may have been missing some critical information in its documentation
(every ontology has its own standards on metadata for terms, design patterns, and so on). You should think hard
about why the AI changes are different from the human changes, and how to improve the instructions to do better in future.

The instructions may refer to external files. You can search these files using the `find_documentation_files` tool,
and then read the contents of the files using the `read_documentation_files` tool. You can use these to suggest changes
that could go in the main documentation file (but don't suggest wholesale copy, the idea is to be minimal).
"""

SHARED_SYSTEM_PROMPT_BODY = """

You will provide your response as markdown text. You can use concice bulleted lists if appropriate. Avoid
unnecessary lengthy verbiage (but at the same time, give specific examples). You should also be clear where you
are making an inference. For example, it's perfectly OK to say "I think the guidelines should mention the rules
of including metadata element X in context Y"

IMPORTANT: always give specific examples at the syntax level. For example, rather than saying "abbreviations should be tagged", you
can provide examples, e.g.

```
synonym: "ABC" EXACT ABBREVIATION [PMID:1234567]
```

There are some areas where the AI and human are EXPECTED to differ - the ID range they use, metadata such as date
of the change, the person making the change. DO NOT suggest changes to the documentation for these.

In some cases the human may have used out-of-band knowledge to make their changes, and it would be impossible
for the AI to replicate. In these cases it is fine to say "no suggestions, it appears that the human 
had additional information that was not provided to the AI."



It is also good to suggest SPECIFIC exemplar obo format stanzas that could be added to the documentation. You can include
more than one if you want to constrast two different patterns that should be distinguished.

Refer to dsign patterns when possible.

In general you will be suggesting additions to the documentation, but you might also want to suggest changes
where the current documentation is incorrect or misleading.
"""

SUMMARIZER_SYSTEM_PROMPT_HEADER = """
Your job is to collate individual suggestions to improve AI documentation into a single new document.
Be specific and concrete in your guidance, giving examples.

If there are explicit documentation gaps you need an expert to fill in, state this.
"""

cborg_api_key = os.environ.get("CBORG_API_KEY")

model = OpenAIModel(
    "anthropic/claude-sonnet",
    provider=OpenAIProvider(
        base_url="https://api.cborg.lbl.gov",
        api_key=cborg_api_key),
)

agent = Agent(
    model=model,
    system_prompt=IMPROVER_SYSTEM_PROMPT_HEADER + SHARED_SYSTEM_PROMPT_BODY,
    retries=2,
)

summarizer_agent = Agent(
    model=model,
    system_prompt=SUMMARIZER_SYSTEM_PROMPT_HEADER + SHARED_SYSTEM_PROMPT_BODY,
    retries=2,
)

@agent.tool_plain
def find_documentation_files(pattern: str) -> list[str]:
    """
    Find documentation files for a given glob pattern.

    Args:
        pattern: The glob pattern to use to find the documentation files.

    Returns:
        A list of file paths.
    """
    import glob
    return glob.glob(pattern)


@agent.tool_plain
def read_documentation_files(files: list[str]) -> dict[str, str]:
    """
    Read the contents of documentation files.

    Args:
        files: A list of file paths.

    Returns:
        A dictionary of file paths and their contents.
    """
    if isinstance(files, str):
        files = [files]
    from pathlib import Path
    return {f: Path(f).read_text() for f in files if Path(f).exists() and Path(f).is_file()}

def propose_documentation_changes(pr_benchmark: PRBenchmark, instructions: str, **kwargs) -> str | None:
    """
    Propose documentation changes for a PR benchmark.

    Args:
        pr_benchmark: The PR benchmark to use.
        instructions: The instructions to use.
        **kwargs: Additional arguments to pass to the agent.

    Returns:
        A string of markdown text describing the changes to make.
    """
    human_diff = pr_benchmark.diff
    if isinstance(human_diff, list):
        human_diff = "\n".join(human_diff)
    ai_diff = pr_benchmark.predicted_diff
    if isinstance(ai_diff, list):
        ai_diff = "\n".join(ai_diff)
    return propose_documentation_changes_impl(pr_benchmark.input_text, instructions, human_diff, ai_diff, **kwargs)

@memory.cache
def propose_documentation_changes_impl(input_text: str, instructions: str, human_diff: str, ai_diff: str, _cache_version: str = "1.1.0", **kwargs) -> str | None:
    if len(input_text) > MAX_ISSUE_TEXT_LENGTH:
        print(f"⚠️  Issue text is {len(input_text)} characters, this may be too long for the model to handle. Truncating to {MAX_ISSUE_TEXT_LENGTH} characters.")
        input_text = input_text[:MAX_ISSUE_TEXT_LENGTH]
    user_prompt = (
        f"Original Issue:\n{input_text}\n\n"
        f"---\nChanges proposed by human expert:\n{human_diff}\n\n"
        f"---\nChanges proposed by AI:\n{ai_diff}\n\n"
        f"---\nOriginal instructions provided to AI:\n{instructions}"
        )
    print(f"🔍 User prompt: {user_prompt}")
    try:
        result = agent.run_sync(
            user_prompt=user_prompt,
            **kwargs
        ).output
    except pydantic_ai.exceptions.ModelHTTPError as e:
        print(f"❌ Error running compare_diffs_impl: {e}")
        if "string too long" in str(e) or "maximum context length" in str(e) or "Input is too long" in str(e):
            print(f"Diff is too long to summarize")
            return
        else:
            raise e
    print(f"💪 Finished propose_documentation_changes_impl: {result}")
    return result


@memory.cache
def summarize_suggestions(instructions: str, suggestions: list[str], _version="1.1.0", **kwargs) -> str:
    """
    Summarize a list of suggestions to improve AI documentation into a single new document.
    """
    user_prompt = (
        f"Original instructions:\n{instructions}\n\n"
        f"---\nSuggestions:\n{suggestions}"
    )
    print(f"🔍 Summarizer user prompt: {user_prompt}")
    result = summarizer_agent.run_sync(user_prompt=user_prompt, **kwargs)
    print(f"✅ Finished summarize_suggestions: {result.output}")
    return result.output