from pydantic import BaseModel, Field
from pydantic_ai import Agent
from joblib import Memory
import pydantic_ai

from ontoeval.models import PRBenchmark

MAX_ISSUE_TEXT_LENGTH = 80_000

memory = Memory('.summarizermemory', verbose=0)

SYSTEM_PROMPT = """
Your job is to summarize a change or set of changes made to an ontology in a PR in response to a user issue(s).

You will be provided the initial issue plus comments that initiated the PR, plus the changes. The changes will
be provided as a list of OWL-level changes. These might be at a quite a low "axiom" level, your job is to summarize.

You should aim to be at a reasonably high level. However, you should still include concrete details, including
both IDs and labels of the terms that were changed.

You should synthesize as far as possible, abstracting up from atomic changes to composite changes; for example, for

```
DELETED: SubClassOf(FOO:1 FOO:2)
ADDED: SubClassOf(FOO:1 FOO:3)
```

You can say "FOO:1 moved from being a subclass of FOO:2 to being a subclass of FOO:3" (including labels if present).

Similarily, pairs of annotations and deletions can sometimes be synthetized further to text-level changes, or even abstracted further;
e.g. you can just report this one as fixing a typo in a definition:

```
DELETED: AnnotationAssertion(IAO:0000115[definition] FOO:1 "A early ...")
ADDED: AnnotationAssertion(IAO:0000115[definition] FOO:1 "An early...")
```

You should avoid using too much OWL in your response. Your audience is used to hearing terminology used in biomedical ontologies,
such as "is_a" and "part_of" relationships (existential restrictions), 
"logical definitions" (for equivalence to intersection of a genus term and existential restriction).
However, if necessary to communicate the full scope of changes, you should shy from using technical or formal language.
Do not sacrifice precision and clarity for simplicity.

Our ontologies make use of axiom annotations, when changes are made to these, you can refer to them as metadata on the assertions.
Sometimes curators will use terms like "definition xrefs" for PMIDs etc on definitions.

Your output should be in markdown format. You can intended yaml in blocks in the standard ways.
Make classes hyperlinked (but display their curie). If you don't know how to hyperlink a CURIE, it's always OK
to use bioregistry.io, e.g. [FOO:1](https://bioregistry.io/FOO:1).

For complex changes involving moving around multiple terms, you can include mermain diagrams in ```mermaid...``` blocks.

You can also make use of bulleted lists (but these are overkill for small changes).

You can use the original issue to weave more of a narrative, around the changes, e.g. "term X was obsoleted in line with
request from user @awesome_ontologist". You should assume that the changes were made correctly, but if changes cannot be
mapped to the original issue, you can say something like "although not explicitly requested, term A was also moved to be
under term B, which is in line with the underlying intent of the issue".

Avoid fluffy content-free summaries, such as "this properly aligns the FOO ontology with the broader goals of FOO science".
You can make precise factual closing statements, e.g. "in total one new term was made, in line with the original request".
Similarly, you can say something like "a misclassification was corrected, improving the ontology", but avoid being blandly
positive.


"""


agent = Agent(
    model="gpt-4o",
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)

def summarize_diff(diff: str | list[str], pr_benchmark: PRBenchmark, **kwargs) -> str:
    """
    Summarize a diff in response to a user issue.

    Args:
        diff: The diff to summarize.
        pr_benchmark: The PR benchmark to use.
        **kwargs: Additional arguments to pass to the agent.
    """
    if isinstance(diff, list):
        diff = "\n".join(diff)
    return summarize_diff_impl(diff, issue_text=pr_benchmark.calculate_input_text(exclude_post_pr_comments=True), **kwargs)

@memory.cache
def summarize_diff_impl(diff: str, issue_text: str, _cache_version: str = "1.0.0", **kwargs) -> str:
    """
    Summarize a diff in response to a user issue (cached version)

    Args:
        diff: The diff to summarize.
        issue_text: The text of the user issue.
        _cache_version: The version of the cache to use (change this in code to invalidate the cache)
        **kwargs: Additional arguments to pass to the agent.

    Returns:
        A string.
    """
    if len(issue_text) > MAX_ISSUE_TEXT_LENGTH:
        print(f"⚠️  Issue text is {len(issue_text)} characters, this may be too long for the model to handle. Truncating to {MAX_ISSUE_TEXT_LENGTH} characters.")
        issue_text = issue_text[:MAX_ISSUE_TEXT_LENGTH]
    try:
        result = agent.run_sync(
            user_prompt=f"Original Issue:\n{issue_text}\n\nDiff:\n{diff}",
            **kwargs
        ).output
    except pydantic_ai.exceptions.ModelHTTPError as e:
        print(f"❌ Error running compare_diffs_impl: {e}")
        if "string too long" in str(e) or "maximum context length" in str(e):
            raise ValueError(f"Diff is too long to summarize: {len(diff)} characters")
        else:
            raise e
    print(f"✅ Finished summarize_diff_impl on {len(diff)} lines:\n```yaml\n{result}\n```")
    return result

