# ontoeval

A python library for creating and running ontology editing tasks for evaluating agentic AI

## How it works

Given a github repository with pull requests (PR) linked to issues, ontoeval will crawl that repo,
and for every PR it will recreate both the state of the repo and the state of the issue tracker at
the point the PR was created. An AI agent is then executed via a **runner**, with the input being the instructions in the linked issues (masking any comments that would not have been visible to the ontology editor who made the original
PR).

The AI agent will then follow these instructions, making edits, and running any tools it has been provided
with. On completion, ontoeval will generate a diff of these changes. This diff can be compared with
the original diff.

## Supported runners

Currently the only supported runner is Goose.

## Experiment configuration

An experiment yaml file should be created that follows the data model in `models.py`

## Evaluators

- metadiff: Simple diff of difffs
- llm_judge: rubric-based evaluation by LLM as judge

## Limitations

### Can not be executed in parallel

ontoeval cannot be executed in parallel (without additional configuration) on the same ontology. This
is because the working directory used to "replay" git commits is shared. If two evaluations are running
at the same time they will conflict in unpredictable ways.

This can be circumvented by creating a second working dir with the same ontology checked out an additional
time. But extreme care should be taken.