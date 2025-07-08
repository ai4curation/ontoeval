from pydantic import BaseModel, Field
from pydantic_ai import Agent
from joblib import Memory
import pydantic_ai
from ontoeval.models import Change, Comparison, PRBenchmark

MAX_ISSUE_TEXT_LENGTH = 80_000

memory = Memory('.judge_memory', verbose=0)

SYSTEM_PROMPT = """
You are a judge that compares two competing proposed changes in response to a user issue.

You will be given a user issue which describes the problem. In some cases this may also include
details on how the problem was ultimately solved, you may used this in your evaluation.

You will be show two proposed changes, a left and a right one. You will need to evaluate the proposed changes
both individually, and also assess consistency between the two proposed changes.

Each proposed change will be in the form of a text diff over obo format. You can infer the changes from the `+` and `-` lines,
plus surrounding context.

For example, if the left change is:

```
 def: "SOME COMMENT HERE" [PMID:12345678]
+is_a: FOO:1234
 creation_date: 2025-01-01
```

and the left change is:

```
 def: "SOME COMMENT HERE" [PMID:12345678]
+relationship: part_of FOO:1234
 creation_date: 2025-01-01
```

Then the two changes differ in the relationship type selected - the  left one chose to insert an is-a edge,
the right one chose to insert a part-of edge (but the parent is the same). When evaluating this particular pair,
you should only consider these differences and report this as being a difference in relationship type selection.
DO NOT COMMENT ON LINES THAT DO NOT CHANGE (here this is the definition, because it is unchanged in both cases).
An exception would be if it is relevant, e.g. in the above example, if
the relationship type is implied by the definition, but even here you would say something like "left changes
are more consistent with the definition".

You should always weight concrete semantic differences over stylistic ones. However, you can note stylistic changes,
differences in grammar, etc, in text fields. Graph placement of the term (is_a and part_of) is of high importance.
The result object you provide has many fields for narrative comments, you should always be as explicit as possible
about your reasoning and back up your scores. Don't say things like "the change is semantically appropriate", this
is vague, instead say something like "the left and right changes different in the choice of relationship type X vs
Y, my interpretation of the issue is that X is more in line with the original request; however, there are some
biological or ontological reasons to prefer Y, so I'm giving a score of 0.5 for the left change and 0.5 for the right change."

You should also take into context ontology-specific best practices and design patterns.

Note that for new term requests, we do not expect the IDs of newly minted terms to match between then two,
these should not count as semantic differences, and you should not prioritize one ID range over the other.

ALWAYS be specific, give concrete examples.
"""

class ProposedChangeEvaluation(BaseModel):
    """
    An evaluation of a proposed change in response to a user issue.

    The proposed change is provided in the form of a text diff
    """
    overall_score: float = Field(
        ..., 
        description="""
        The overall score of the proposed change, in terms of how well it addressed the issue, biological correctness, 
        and adherence to ontology design principles.
        """
    )
    evaluation: str = Field(..., description="Overall evaluation of the proposed change. BE SPECIFIC, GIVE CONCRETE EXAMPLES. Refer to the issue text and quote where relevant.")
    instruction_following_score: float = Field(..., ge=0, le=1, description="How well the results followed the instructions, between 0 and 1.")
    incorrect_changes: list[str] = Field(..., description="The incorrect changes that were made in the proposed change.")
    missing_changes: list[str] = Field(..., description="The necessary missing changes that were not made in the proposed change.")
    

class LLMJudgeComparison(Comparison):
    """
    An evaluation of a pair of competing proposed changes in response to a user issue.
    """
    similarity: float = Field(..., ge=0, le=1, description="The similarity score between the two diffs, between 0 and 1.")
    difficulty: float = Field(..., ge=0, le=1, description="The overall difficulty of the issue, between 0 and 1. 0 is a trivial single-line change, 1 is a complex multi-line multi-file change, with decision making.")
    issue_clarity: float = Field(..., ge=0, le=1, description="How clear was the task described in the issue? 0 is a very unclear issue, 1 is a very clear issue.")
    logical_consistency: float = Field(..., ge=0, le=1, description="The logical consistency score between the two diffs, between 0 and 1.")
    confidence: float = Field(..., description="Your own confidence in the correctness of your evaluation, between 0 and 1.")
    suggestions_for_users: str = Field(..., description="""
                                       How could the issue have been worded to avoid confusion and improve clarity.
                                       BE SPECIFIC, GIVE CONCRETE EXAMPLES.
                                       """)
    left_evaluation: ProposedChangeEvaluation = Field(..., description="The evaluation of the proposed change in the left diff.")
    right_evaluation: ProposedChangeEvaluation = Field(..., description="The evaluation of the proposed change in the right diff.")
    score_diff: float | None = Field(None, ge=-1, le=1, description="left_evaluation.overall_score - right_evaluation.overall_score (do not set manually)")
    instruction_following_score_diff: float | None = Field(None, ge=-1, le=1, description="left_evaluation.instruction_following_score - right_evaluation.instruction_following_score (do not set manually)")
    comments: str = Field(..., description="Any additional comments you want to make about the evaluation. Be specific, give concrete examples.")

    def set_score_diff(self):
        self.score_diff = self.left_evaluation.overall_score - self.right_evaluation.overall_score
        self.instruction_following_score_diff = self.left_evaluation.instruction_following_score - self.right_evaluation.instruction_following_score

agent = Agent(
    model="gpt-4o",
    output_type=LLMJudgeComparison,
    system_prompt=SYSTEM_PROMPT,
    retries=3,
)

def compare_diffs(diff1: str | list[str], diff2: str | list[str], pr_benchmark: PRBenchmark, **kwargs) -> LLMJudgeComparison:
    return compare_diffs_impl(diff1, diff2, issue_text=pr_benchmark.calculate_input_text(exclude_post_pr_comments=False), **kwargs)

@memory.cache
def compare_diffs_impl(diff1: str | list[str], diff2: str | list[str], issue_text: str, _cache_version: str = "1.3.0", **kwargs) -> LLMJudgeComparison:
    """
    Compare two diffs in response to a user issue.

    Args:
        diff1: The first diff to compare.
        diff2: The second diff to compare.
        issue_text: The text of the user issue.
        _cache_version: The version of the cache to use (change this in code to invalidate the cache)
        **kwargs: Additional arguments to pass to the agent.

    Returns:
        A LLMJudgeComparison object.
    """
    if isinstance(diff1, list):
        diff1 = "\n".join(diff1)
    if isinstance(diff2, list):
        diff2 = "\n".join(diff2)
    print(f"⚖️  Running compare_diffs_impl on {len(diff1)} lines and {len(diff2)} lines")
    if len(issue_text) > MAX_ISSUE_TEXT_LENGTH:
        print(f"⚠️  Issue text is {len(issue_text)} characters, this may be too long for the model to handle. Truncating to {MAX_ISSUE_TEXT_LENGTH} characters.")
        issue_text = issue_text[:MAX_ISSUE_TEXT_LENGTH]
    try:
        result = agent.run_sync(
            user_prompt=f"User Issue:\n{issue_text}\n\nLeft Diff:\n{diff1}\n\nRight Diff:\n{diff2}",
            **kwargs
        ).output
    except pydantic_ai.exceptions.ModelHTTPError as e:
        print(f"❌ Error running compare_diffs_impl: {e}")
        if "string too long" in str(e) or "maximum context length" in str(e):
            
            result = LLMJudgeComparison(
                overall_score=0.0,
                evaluation="STRING TOO LONG",
                similarity=0.0,
                difficulty=0.0,
                issue_clarity=0.0,
                logical_consistency=0.0,
                confidence=0.0,
                suggestions_for_users="STRING TOO LONG",
                left_evaluation=ProposedChangeEvaluation(
                    overall_score=0.0,
                    
                    evaluation="STRING TOO LONG",
                    instruction_following_score=0.0,
                    incorrect_changes=[],
                    missing_changes=[],
                ),
                right_evaluation=ProposedChangeEvaluation(
                    overall_score=0.0,
                    evaluation="STRING TOO LONG",
                    instruction_following_score=0.0,
                    incorrect_changes=[],
                    missing_changes=[],
                ),
                comments="STRING TOO LONG",
            )
        else:
            raise e
    result.set_score_diff()
    import yaml
    print(f"✅ Finished compare_diffs_impl on {len(diff1)} lines and {len(diff2)} lines:\n```yaml\n{yaml.dump(result.model_dump(exclude_none=True))}\n```")
    return result

