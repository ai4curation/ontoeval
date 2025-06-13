from typing import Iterator
from ontoeval.judges.metadiff_judge import MetadiffComparison
from ontoeval.judges.llm_judge import LLMJudgeComparison
from ontoeval.models import Change, PRBenchmark

import yaml

def render_result(r: PRBenchmark) -> str:
    """
    Render a PRBenchmark as a markdown string.
    """
    return "\n".join(render_result_iter(r))

def render_change(chg: Change) -> str:
    """
    Render a change as a markdown string.
    """
    dirn, text = chg
    if dirn == 1:
        txt = "ADD"
    else:
        txt = "DEL"
    return f"- {txt} :: `{text}`\n"

def render_result_iter(r: PRBenchmark) -> Iterator[str]:
    """
    Render a PRBenchmark as a markdown string.
    """

    md_judge : MetadiffComparison = r.comparisons["metadiff_judge"]
    llm_judge : LLMJudgeComparison = r.comparisons.get("llm_judge")
    yield f"# {r.pr_number} - {r.title}"
    yield f"\n - [{r.url}]({r.url})\n"
    yield f"\n{r.body}\n"

    yield f"## Metadiff ({md_judge.similarity})\n"
    yield md_judge.metadiff_color_html

    yield "Unique to target:\n"
    for change in md_judge.changes_in_diff1:
        yield render_change(change)

    yield "Unique to prediction:\n"
    for change in md_judge.changes_in_diff2:
        yield render_change(change)

    yield f"## LLM Judge\n"
    
    yield "```yaml"
    yield yaml.dump(llm_judge.model_dump())
    yield "```"

    yield "\n## Issues\n" 
    for issue in r.linked_issues:
        yield f"- [{issue.title}]({issue.url})\n"
        yield issue.body
