# ontoeval

A python library for evaluating the performance of AI agents on ontology tasks, using GitHub issues and pull requests as a benchmark

## ℹ️ How it works

Given a github repository with pull requests (PR) linked to issues, ontoeval will crawl that repo,
and for every PR it will recreate both the state of the repo and the state of the issue tracker at
the point the PR was created. An AI agent is then executed via a **runner**, with the input being the instructions in the linked issues (masking any comments that would not have been visible to the ontology editor who made the original
PR).

The AI agent will then follow these instructions, making edits, and running any tools it has been provided
with. On completion, ontoeval will generate a diff of these changes. This diff can be compared with
the original diff.

## 🏃 Supported runners

A runner is an agentic AI application that can use tools to perform a task.

Currently the following are supported:

- Claude Code
- Goose (CLI version)

## ⚗️ Experiment configuration

An experiment yaml file should be created that follows the data model in `models.py`

Here is an example config for testing goose as a runner over Mondo:

`mondo-1.yaml`:

```yaml
type: ontoeval.runners.goose.GooseRunner
env:
  PATH: "$PATH"
repo: monarch-initiative/mondo
name: mo-son4-gs
description: First run for mondo, using bedrock/claude
prompt: |
  Resolve the following issue to the best of your abilities. DO NOT use
  git, gh, or github tools to fulfil this task.

  IMPORTANT: DO NOT `git commit` at the end of the task. I will evaluate the modifications
  you have made before committing.
  
  Here is the issue history, remember the most recent comments at the bottom
  may be the most relevant:
  {input_text}
```

Additionally there should be a directory layout:

 * `mondo-1.yaml`
 * `mondo-1/`
     * `results`
     * `config`

The results folder will start empty. The contents of the config folder depends on the runner. The contents are copied to the working dir checkout
of the ontology before each run.  

## ⚖️ Running an experiment

```
ontoeval run-all \
  -c experiments/mondo-1.yaml \
  -I src/ontology/mondo-edit.obo \
  -o experiments//mondo-1/results/results.json 
  --markdown-directory experiments/mondo-1/results/markdown \
  -l 100
```

## ⚖️  Example of use

see odk-ai-ontoeval repo

## ⚖️  Evaluators

There are multiple ways to evaluate an AI generated PR. Currently we have two rubrics:

- metadiff: Simple diff of difffs, includes scores for overlap, f1, precision, recall
- llm_judge: rubric-based evaluation by LLM as judge

In both cases, we compare against the human generated PR (which was hidden from the AI). The metadiff looks at the similarity of changes made
by the AI and the human. Some parts of the PR are redacted or modified - e.g. for new terms, we expect these to have different numeric parts, so
these are normalized to a new range.

Example:

```yaml
```

One limitation of the metadiff is that each line/axiom is treated as all or nothing. If the AI and human propose very similar changes to a long text definition, but they differ in a single character, then this is treated as both a false positive AND a false negative. A more sophisticated strategy would be
to use some kind of similarity metric like BLEU on textual fields, but this is not implemented.

The LLM judge presents the issue plus both human and AI changes to an LLM and asks for an evaluation using multiple criteria.

Example:

```yaml
comments: Both proposals make appropriate conceptual changes, adding part-of relationships
  which are logical for biological descriptions. The left proposal stays more precise
  in its selection of the parent term. Further refinement with supporting annotations
  or additional axioms would enhance both proposals.
confidence: 0.9
difficulty: 0.6
issue_clarity: 0.7
left_evaluation:
  evaluation: 'The left proposal adds a ''relationship: part_of'' to the parent ''UBERON:0002616''.
    This addition is semantically appropriate as it captures the part-whole relationship
    expected in this biological context. However, it lacks additional context-specific
    assertions or further ontology axioms that could provide deeper semantic understanding.'
  incorrect_changes:
  - None
  instruction_following_score: 0.9
  missing_changes:
  - Additional context-specific annotations or supporting axioms.
  overall_score: 0.7
logical_consistency: 0.8
right_evaluation:
  evaluation: 'The right proposal modifies the term by adding a ''relationship: part_of''
    but points to a slightly different parent, ''UBERON:0002619''. While this is still
    contextually relevant, there is less precision compared to the left proposal.
    The right addition is good but slightly less specific or perhaps slightly more
    incorrect compared to the left.'
  incorrect_changes:
  - Parent term is slightly less precise.
  instruction_following_score: 0.9
  missing_changes:
  - Additional context-specific annotations or supporting axioms.
  overall_score: 0.6
score_diff: 0.09999999999999998
similarity: 0.8
suggestions_for_users: To improve clarity, the user could have provided explicit criteria
  for relationship types and any conditions under which specific patterns should be
  used. For example, stating explicitly if a certain relationship type or pattern
  is preferred for certain biological processes.
```

## ⚠️ Limitations

### Can not be executed in parallel

ontoeval cannot be executed in parallel (without additional configuration) on the same ontology. This
is because the working directory used to "replay" git commits is shared. If two evaluations are running
at the same time they will conflict in unpredictable ways.

This can be circumvented by creating a second working dir with the same ontology checked out an additional
time. But extreme care should be taken.

### Single issue assumption

The evaluation code assumes a one to one correspondence between issues and PRs. However, real-world
work often involves more complex divisions. This can potentially confound evaluation.

If a single issue has multiple PRs associated, this is tagged as an `epic`, and it these PRs are
ignored for evaluation purposes. In future, the evaluation framework could take the agent-generated PR
and compare it against the sum total of actual PRs for that issue.