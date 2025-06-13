from pydantic import BaseModel, Field
from pydantic_ai import Agent
from joblib import Memory
from ontoeval.models import Change, Comparison, PRBenchmark

memory = Memory('.judge_memory', verbose=0)

SYSTEM_PROMPT = """
You are a judge that compares two competing proposed changes in response to a user issue.

You will be given a user issue which describes the problem. In some cases this may also include
details on how the problem was ultimately solved, you may used this in your evaluation.

You will be show two proposed changes, a left and a right one. You will need to evaluate the proposed changes
both individually, and also assess consistency between the two proposed changes.

The proposed change will be in the form of a text diff.

You should always weight concrete semantic differences over stylistic ones. However, you can note stylistic changes,
differences in grammar, etc, in text fields. Graph placement of the term (is_a and part_of) is of high importance.

You should also take into context ontology-specific best practices and design patterns.

Note that for new term requests, we do not expect the IDs of newly minted terms to match between then two,
these should not count as semantic differences, and you should not prioritize one ID range over the other.
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
    evaluation: str = Field(..., description="Overall evaluation of the proposed change.")
    incorrect_changes: list[str] = Field(..., description="The incorrect changes that were made in the proposed change.")
    missing_changes: list[str] = Field(..., description="The necessary missing changes that were not made in the proposed change.")
    

class LLMJudgeComparison(Comparison):
    """
    An evaluation of a pair of competing proposed changes in response to a user issue.
    """
    similarity: float = Field(..., description="The similarity score between the two diffs, between 0 and 1.")
    difficulty: float = Field(..., description="The overall difficulty of the issue, between 0 and 1. 0 is a trivial single-line change, 1 is a complex multi-line multi-file change, with decision making.")
    issue_clarity: float = Field(..., description="How clear was the task described in the issue? 0 is a very unclear issue, 1 is a very clear issue.")
    logical_consistency: float = Field(..., description="The logical consistency score between the two diffs, between 0 and 1.")
    confidence: float = Field(..., description="Your own confidence in the correctness of your evaluation, between 0 and 1.")
    suggestions_for_users: str = Field(..., description="How could the issue have been worded to avoid confusion and improve clarity.")
    left_evaluation: ProposedChangeEvaluation = Field(..., description="The evaluation of the proposed change in the left diff.")
    right_evaluation: ProposedChangeEvaluation = Field(..., description="The evaluation of the proposed change in the right diff.")
    score_diff: float = Field(..., description="left_evaluation.overall_score - right_evaluation.overall_score (do not set manually)")
    comments: str = Field(..., description="Any additional comments you want to make about the evaluation.")

    def set_score_diff(self):
        self.score_diff = self.left_evaluation.overall_score - self.right_evaluation.overall_score


agent = Agent(
    model="gpt-4o",
    output_type=LLMJudgeComparison,
    system_prompt=SYSTEM_PROMPT,
    retries=3,
)

def compare_diffs(diff1: str | list[str], diff2: str | list[str], pr_benchmark: PRBenchmark, **kwargs) -> LLMJudgeComparison:
    return compare_diffs_impl(diff1, diff2, pr_benchmark.calculate_input_text(exclude_post_pr_comments=False), **kwargs)

@memory.cache
def compare_diffs_impl(diff1: str | list[str], diff2: str | list[str], issue_text: str, **kwargs) -> LLMJudgeComparison:
    if isinstance(diff1, list):
        diff1 = "\n".join(diff1)
    if isinstance(diff2, list):
        diff2 = "\n".join(diff2)
    prompt = f"""
    User Issue:
    {issue_text}
    """
    return agent.run_sync(
        input=f"Left Diff:\n{diff1}\n\nRight Diff:\n{diff2}",
        **kwargs
    ).output

