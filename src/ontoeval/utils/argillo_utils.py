import yaml
from ontoeval.judges.metadiff_judge import ansi_to_html
from ontoeval.models import PRBenchmark, UserEvalTask
from ontoeval.runner import AgentConfig
from ontoeval.utils.diff_summarizer import summarize_diff
from ontoeval.utils.diff_utils import apply_redaction_mask, get_redaction_mask_from_diff
from ontoeval.utils.replay_diff import replay_diff
import argilla as rg

GUIDELINES = """

### Overview

Your task as evaluator is to evaluate and review the proposed changes to the ontology, based on
the instructions provided in the form of a GitHub issue. Each evaluation *task* is a combination
of *issues* (the original GitHub issue) and a *proposed solution* (a real or simulated PR).
Each task also has a *title* that includes the PR and title.

### Left Panel

The evaluation task is presented in the following sections:

1. Issue text
    - in some cases, this is a concise simple description of a proposed action
    - in other cases, it may be a long-running discussion
2. Proposed solution, as a **colored ascii diff**
    - this is intended to simulate how diffs look in GitHub PRs
    - Use this if you are familiar with the obo format text diffs in PRs
    - In some cases, a text-diff is too low level, so you may want to look at the OWL axioms
3. Proposed solution, as a set of changes given as **OWL axioms**
    - See [robot diff](https://robot.obolibrary.io/docs/diff/) for more details
    - Use this if you are familiar with OWL and OWL axioms
    - Here the 'left' ontology is the ontology *prior* to the proposed changes, and the 'right' ontology is after the proposed changes are applied
4. AI-generated higher level summary of the changes

These three solution formats are provided for your convenience.
You only need to look at ONE of these. If you are used to looking at obo format text diffs, then
this will likely be sufficient for you. If you are used to OWL axioms, then the second may be best.
If you want a high-level summary of the changes, then the AI summary may be best. 
Note your job is NOT to evaluate the summary itself.

Some details may be masked/redacted from the diff. For example, the IDs of new terms, or
 information about the person or agent who made the changes. You are not being asked to evaluate
 on these aspects.


### Right Panel

This is where you provide your evaluation.

As far as possible, you should place yourself in the job of an ontology PR reviewer. If you have been
 selected to evaluate, we assume you are familiar with ontology PR reviews. However, each ontology differs
 somewhat in its practice. We recommend reading 
 [How to review a pull request](https://oboacademy.github.io/obook/tutorial/pull-requests/?h=pull+requests#how-to-review-a-pull-request-pr)
 in the OBO Academy OBook for some guidance.


The allowed review actions are::

- merge:
    - no modifications needed
    - Proposed PR can be merged into the ontology as-is
    - This should be considered the same as 'merge' in the GitHub UI
    - If you select this, you do not need to provide comments (but you can if you want to)
- minor:
    - minor changes needed to be complete/correct
    - This might be considered the same as 'request changes' in the GitHub UI, although depending on preference it may correspond to a merge with future PRs patching missing info
    - example: changes in wording of comments or definitions
    - If you select this, you should indicate in the comments what the minor changes are
- major:
    - major changes needed to be complete/correct
    - This might be considered the same as 'request changes' in the GitHub UI, but in some cases it may be easier to start again
    - example: missing key metadata fields (e.g. link to issue tracker, obsoletion metadata)
    - example: adding missing logical axioms or major relationships
    - If you select this, you should indicate in the comments what the major changes are
- reject:
    - the PR is wrong, or on the entirely wrong track
    - This should be considered the same as 'close' in the GitHub UI
    - example: the proposed changes involved making new relationships that are objectively wrong
    - If you select this, you can specify in the comments what the error(s) are
- no action:
    - defer on this PR
    - select this if you think further research or discussion is required to determine the right course of action
    - select this if the upstream issue is unclear or lacks consensus, or if clarification from the issue author is required
    - select this if you think you lack the expertise to fully evaluate the PR
    - You may indicate your reason for deferring in the comments, but this is optional

You are NOT expected to perform additional lookups or research beyond what is provided in the issue text.
The assumption is that general biological knowledge plus what is in the ticket text is sufficient. If you
do additional research, please indicate this by selecting the 'additional lookups performed?' question,
and noting what you did in the comments.
    
Additionally, you will be asked if you are familiar with the issue. Perhaps you wrote the issue, perhaps
you engaged in discussion on the issue, or perhaps you are the original author of a PR for this issue.

"""

ACTION_LABELS = {
    "merge": "no modifications needed. Proposed PR should be merged into the ontology as-is",
    "minor": "*minor* changes needed to be complete/correct",
    "major": "*major* changes needed to be complete/correct",
    "reject": "the PR is wrong, or on the entirely wrong track",
    "no action": "further research is necessary",
}

def get_settings(min_submitted=5) -> rg.Settings:
    settings = rg.Settings(
        guidelines=GUIDELINES,
        fields=[
            rg.TextField(
                name="title",
            ),
            rg.TextField(
                name="description",
                use_markdown=True,
            ),
            rg.TextField(
                name="id",
            ),
        ],
        questions=[
            rg.LabelQuestion(
                name="action", 
                labels=ACTION_LABELS,
                required=True, 
                description="Should the proposed changes be merged into the ontology?"
                ),
            rg.LabelQuestion(
                name="additional lookups performed?", 
                labels={
                    "no": "No (this should be the case for most tasks)",
                    "yes": "Yes, I performed additional research or lookups",
                },
                required=True, 
                description="Did you use additional information not provided in the issue text to make your decision. In general this should NOT be necessary, and you should evaluate based on the information provided"
                ),
            rg.LabelQuestion(
                name="familiar with this issue?", 
                labels={
                    "1": "Yes, I am the author of this issue or the corresponding PR, or I reviewed the original PR",
                    "2": "I am familiar with the issue, but am not the main issue or PR author",
                    "3": "I am unfamiliar with this specific issue, but I am confident or reasonably confident in evaluating it",
                    "4": "I am unfamiliar with this specific issue, but I am confident or reasonably confident in evaluating it",
                    "yes": "Yes, I recognize this issue, and it is partly or completely outside my area of expertise",
                },
                required=True, 
                description="Are you familiar with the issue from working on the ontology?",
                ),        
            rg.TextQuestion(
                name="comments",
                title="Futher comments",
                description="Please explain your rating or add any notes",
                required=False
            ),
        ],
        allow_extra_metadata=True,
        # This is the key setting:
        distribution=rg.TaskDistribution(min_submitted=min_submitted),
    )
    return settings
    

def create_task(agent: AgentConfig, r: dict, max_diff_size_lines: int, exclude_terms: list[str] | None = None) -> list[UserEvalTask]:
    human_diff = r["diff"]

    if len(human_diff.splitlines()) > max_diff_size_lines:
        print(f"🚫 Skipping PR #{r['pr_number']} because the human diff is too large: {len(human_diff.splitlines())} lines")
        return []
    ai_diff = r["predicted_diff"]
    if len(ai_diff.splitlines()) > max_diff_size_lines:
        print(f"🚫 Skipping PR #{r['pr_number']} because the AI predicted diff is too large: {len(ai_diff.splitlines())} lines")
        return


    pr = PRBenchmark(**r)
    if exclude_terms:
        for term in exclude_terms:
            txt = pr.body + " " + pr.get_comment_text()
            if term.lower() in txt.lower():
                print(f"🚫 Skipping PR #{r['pr_number']} because it contains the term {term} in the comments")
                return []
    
    tasks = []
    # set version to be a random int between 1 and 10
    import random
    version = random.randint(1, 10)
    for (is_ai, diff) in [(False, human_diff), (True, ai_diff)]:

        mask = get_redaction_mask_from_diff(diff)

        pr_number = r["pr_number"]
        files_to_compare = [f for f in r["files_changed"] if f.endswith(".obo") or f.endswith(".owl") or f.endswith(".ofn")]
        print(f"🔍 Files to compare for PR #{pr_number}: {files_to_compare}")
        diff_result = replay_diff(agent.repo_local_path(), r["base_commit"], diff, files_to_compare=files_to_compare)
        if not diff_result.robot_diff_map:
            print(f"🚫 Skipping PR #{r['pr_number']} because the robot diff is empty for {len(diff.splitlines())} lines")
            return
        print(f"🔍 Diff result for {r['pr_number']}:\n```yaml")
        print(yaml.dump(diff_result.model_dump()))
        print("```")

        description = "Evaluate the solution given the background issues\n\n## 1. ISSUE TEXT:\n"
        
        replacement_texts = []
        for issue in pr.linked_issues:
            description += f" - {issue.title}\n"
            replacement_texts.append( (f"Issue {issue.number}", f"Issue NNNN") )
        all_issue_text = pr.calculate_input_text()
        for (old, new) in replacement_texts:
            all_issue_text = all_issue_text.replace(old, new)
        description += all_issue_text

        description += "\n\n## 2. PROPOSED SOLUTION (ascii diff ):\n\n```diff\n"
        description += apply_redaction_mask(diff, mask)
        description += "\n```\n"

        #description += "\n\n## 3. PROPOSED SOLUTION (colored diff ):\n\n```yaml\n"
        #for k, v in diff_result.icdiff_diff_map.items():
        #    description += f"### {k}\n"
        #    v_masked = apply_redaction_mask(v, mask)
        #    #v_masked_html = ansi_to_html(v_masked)
        #    description += f"```\n{v_masked}\n```\n"

        robot_diffs = []
        description += "\n\n## 4. PROPOSED SOLUTION (as ROBOT diff):\n"
        for k, v in diff_result.robot_diff_map.items():
            v_masked = apply_redaction_mask(v, mask)
            description += f"### {k}\n"
            description += v_masked
            robot_diffs.append(v_masked)

        # LLM summarize the diffs
        summary = summarize_diff(robot_diffs, pr)
        description += f"\n\n## 5. AI SUMMARY OF PROPOSED SOLUTION:\n\n{summary}"

        unhidden_id = f"{r['experiment_id']}_{pr_number}_{'ai' if is_ai else 'human'}"
        # we will use base64 encoding to hide the id from the user
        import base64
        id = base64.b64encode(unhidden_id.encode()).decode()
        task = UserEvalTask(
            id=id,
            unhidden_id=unhidden_id,
            title=f"PR #{pr_number} -- {r['title']} (v{version})",
            repo=agent.repo,
            description=description,
            experiment_id=r["experiment_id"],
            pr_number=pr_number,
            is_ai=is_ai,
        )
        version += (random.randint(1, 8) % 10) + 1
        tasks.append(task)

    return tasks