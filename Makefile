MAKEFLAGS += --warn-undefined-variables
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
.SUFFIXES:
.SECONDARY:

RUN = uv run
SRC = src
DOCDIR = docs

.PHONY: all clean test lint format install example help

help:
	@echo ""
	@echo "make all -- makes site locally"
	@echo "make install -- install dependencies"
	@echo "make test -- runs tests"
	@echo "make lint -- runs linters"
	@echo "make format -- formats the code"
	@echo "make testdoc -- builds docs and runs local test server"
	@echo "make deploy -- deploys site"
	@echo "make example -- runs the example script"
	@echo "make help -- show this help"
	@echo ""

setup: install

install:
	uv sync --all-extras

all: test lint format

test: pytest doctest

pytest:
	$(RUN) pytest tests/

DOCTEST_DIR = src
doctest:
	$(RUN) pytest --doctest-modules src/ontoeval

lint:
	$(RUN) ruff check .

format:
	$(RUN) ruff format .

# Test documentation locally
serve: mkd-serve

deploy: mkd-deploy

# Deploy docs
deploy-doc:
	$(RUN) mkdocs gh-deploy

# docs directory
$(DOCDIR):
	mkdir -p $@

MKDOCS = $(RUN) mkdocs
mkd-%:
	$(MKDOCS) $*

example:
	$(RUN) python example.py

clean:
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf site/

# Analysis

Q = query -l 999999


LAST_PR_GO = 30446

experiments/go-goose-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-1.yaml -I src/ontology/go-edit.obo -o $@ -l $*
.PRECIOUS: experiments/go-goose-1/results/results-%.json

experiments/go-goose-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-2.yaml -I src/ontology/go-edit.obo -o $@ -l $*
.PRECIOUS: experiments/go-goose-2/results/results-%.json

experiments/go-goose-3/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-3.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-3/results/markdown -S $(LAST_PR_GO)  -l $*
.PRECIOUS: experiments/go-goose-3/results/results-%.json

experiments/go-goose-4/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-4.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-4/results/markdown -S $(LAST_PR_GO)  -l $*
.PRECIOUS: experiments/go-goose-4/results/results-%.json

# o3
experiments/go-goose-5/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-5.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-5/results/markdown  -l $*
.PRECIOUS: experiments/go-goose-5/results/results-%.json

experiments/go-claude-6/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-claude-6.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-claude-6/results/markdown  -l $*
.PRECIOUS: experiments/go-claude-6/results/results-%.json

# qwq
experiments/go-goose-7/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-7.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-7/results/markdown  -S $(LAST_PR_GO)  -l $*
.PRECIOUS: experiments/go-goose-7/results/results-%.json

# OLD: opus
experiments/go-goose-8/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-8.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-8/results/markdown  -l $* -S 30379
.PRECIOUS: experiments/go-goose-8/results/results-%.json

# o4-mini/codex
experiments/go-9/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-9.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-9/results/markdown  -l $* -S $(LAST_PR_GO)
.PRECIOUS: experiments/go-9/results/results-%.json

#llama4
experiments/go-10/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-10.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-10/results/markdown  -l $* -S 30379
.PRECIOUS: experiments/go-10/results/results-%.json

# opus
experiments/go-11/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-11.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-11/results/markdown  -l $* -S 30400
.PRECIOUS: experiments/go-11/results/results-%.json

# opus-sonnet
experiments/go-13/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-13.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-13/results/markdown  -l $* -S $(LAST_PR_GO)
.PRECIOUS: experiments/go-13/results/results-%.json

# gemini
experiments/go-14/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-14.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-14/results/markdown  -l $* -S $(LAST_PR_GO)
.PRECIOUS: experiments/go-14/results/results-%.json

# codex/o3
experiments/go-15/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-15.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-15/results/markdown  -l $* -S $(LAST_PR_GO)
.PRECIOUS: experiments/go-15/results/results-%.json


experiments/uberon-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-1.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-1/results/markdown  -l $*
.PRECIOUS: experiments/uberon-1/results/results-%.json

experiments/uberon-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-2.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-2/results/markdown  -l $*
.PRECIOUS: experiments/uberon-2/results/results-%.json

experiments/uberon-3/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-3.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-3/results/markdown  -l $*
.PRECIOUS: experiments/uberon-3/results/results-%.json

# gs, sonn4, cborg
experiments/uberon-4/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-4.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-4/results/markdown  -l $*
.PRECIOUS: experiments/uberon-4/results/results-%.json

experiments/mondo-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-1.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-1/results/markdown  -l $*
.PRECIOUS: experiments/mondo-1/results/results-%.json

experiments/mondo-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-2.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-2/results/markdown  -l $*
.PRECIOUS: experiments/mondo-2/results/results-%.json

experiments/mondo-3/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-3.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-3/results/markdown  -l $* -S 9041
.PRECIOUS: experiments/mondo-3/results/results-%.json

experiments/mondo-4/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-4.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-4/results/markdown  -l $* -S 9041
.PRECIOUS: experiments/mondo-3/results/results-%.json


experiments/po-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/po-1.yaml -I plant-ontology.obo -o $@ -l $*
.PRECIOUS: experiments/po-1/results/results-%.json


experiments/fb-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/fb-1.yaml -I src/ontology/fbbt-edit.obo --markdown-directory experiments/fb-1/results/markdown -o $@ --markdown-directory experiments/fb-1/results/markdown -l $*
.PRECIOUS: experiments/fb-1/results/results-%.json

EVALDIR = ../odk-ai-evals/docs


sync-uberon:
	cp -pr experiments/uberon-2/results/markdown/* $(EVALDIR)/uberon/

# Generic experiments stats


# TODO: ensure always rebuilt
experiments/%.duckdb: experiments/%.json
	shep -d $@ -c main insert $<

experiments/%.fq.yaml: experiments/%.duckdb
	shep -d $< fq -O yaml -o $@

experiments/%.fq.png: experiments/%.duckdb
	shep -d $< fq -O png -o $@

experiments/%.xlsx: experiments/%.duckdb
	shep -d $< $(Q) -o $@ -O xlsx

experiments/%.jsonl: experiments/%.duckdb
	shep -d $< $(Q) -o $@ -O jsonl

experiments/%.dbc.png: experiments/%.jsonl
	shep plot diverging-barchart $< -y title -x llm_judge_score_diff -w 10 -h 20 --title "AI vs Human" -o $@

experiments/%.boxplot.f1.png: experiments/%.jsonl
	shep plot boxplot  $< -y title -x metadiff_judge_f1_score -w 10 -h 20 -o $@

experiments/%.boxplot.sd.png: experiments/%.jsonl
	shep plot boxplot  $< -y title -x llm_judge_score_diff -w 10 -h 20 -o $@

experiments/%.hist.sim.png: experiments/%.jsonl
	shep plot histogram -b 20  $< -x metadiff_judge_similarity -o $@

experiments/%.hist.sim2.png: experiments/%.jsonl
	shep plot histogram -b 20  $< -x llm_judge_similarity -o $@

experiments/%.hist.scorediff.png: experiments/%.jsonl
	shep plot histogram -b 20  $< -x llm_judge_score_diff -o $@

experiments/%.scatter.sd.png: experiments/%.jsonl
	shep plot scatterplot --include-correlation  $< -x llm_judge_difficulty -y llm_judge_score_diff -o $@

experiments/%.scatter.ss.png: experiments/%.jsonl
	shep plot scatterplot --include-correlation  $< -x llm_judge_similarity -y metadiff_judge_similarity -o $@

experiments/%.scatter.cost-v-hardness.png: experiments/%.jsonl
	shep plot scatterplot --include-correlation  $< -y agent_output_total_cost_usd  -x llm_judge_difficulty -o $@

experiments/%.scatter.cost-v-nc.png: experiments/%.jsonl
	shep plot scatterplot --include-correlation  $< -y agent_output_total_cost_usd  -x number_of_issue_comments -o $@

experiments/%.all: experiments/%.fq.yaml experiments/%.fq.png experiments/%.xlsx experiments/%.hist.sim.png experiments/%.hist.sim2.png  experiments/%.hist.scorediff.png experiments/%.scatter.sd.png experiments/%.scatter.ss.png experiments/%.scatter.cost-v-hardness.png experiments/%.scatter.cost-v-nc.png experiments/%.dbc.png experiments/%.boxplot.f1.png
	echo done

# enhance instructions
experiments/%.enhanced-instructions.o3.md: experiments/%.json
	uv run ontoeval improve -m openai:o3 $<  -J experiments/$*-suggestions.json -o $@

experiments/%.enhanced-instructions.o4-mini.md: experiments/%.json
	uv run ontoeval improve -m openai:o4-mini $<  -J experiments/$*-suggestions.json -o $@

# Comparisons

GO_MINIMAL_INSTRUCTIONS = experiments/go-goose-1/results/results-300.json
GO_GOOSE_SONNET = experiments/go-goose-3/results/results-250.json
GO_GOOSE_GPT4O = experiments/go-goose-4/results/results-300.json
GO_GOOSE_O3 = experiments/go-goose-5/results/results-334.json
GO_CLAUDECODE_SONNET = experiments/go-claude-6/results/results-100.json
GO_GOOSE_OPUS = experiments/go-11/results/results-10.json
GO_GEMINI = experiments/go-14/results/results-30.json

comparisons/%/heatmap.f1.png: comparisons/%.json
	linkml-store plot heatmap comparisons/$*/scores.csv  -y title -x experiment_id -v metadiff_judge_f1_score -o $@

comparisons/%/heatmap.sd.png: comparisons/%.json
	linkml-store plot heatmap comparisons/$*/scores.csv  -y title -x experiment_id -v llm_judge_score_diff -o $@

comparisons/%/boxplot.f1.png: comparisons/%.json
	linkml-store plot boxplot comparisons/$*.json -y title -x metadiff_judge_f1_score -w 10 -h 20 -o $@

comparisons/%/boxplot.sim.png: comparisons/%.json
	linkml-store plot boxplot comparisons/$*.json -y title -x metadiff_judge_similarity -w 10 -h 20 -o $@

comparisons/%/boxplot.sd.png: comparisons/%.json
	linkml-store plot boxplot comparisons/$*.json -y title -x llm_judge_score_diff -w 10 -h 20 -o $@


comparisons/%/all: comparisons/%/heatmap.f1.png comparisons/%/heatmap.sd.png comparisons/%/boxplot.f1.png comparisons/%/boxplot.sim.png  comparisons/%/boxplot.sd.png
	echo hi1

comparisons/go-no-instr.json: 
	uv run ontoeval combine -c metadiff_judge_similarity $(GO_CLAUDECODE_SONNET) $(GO_MINIMAL_INSTRUCTIONS) -o $@

# all 4 GO experiments
comparisons/go-all.json:
	uv run ontoeval combine  $(GO_GOOSE_SONNET) $(GO_GOOSE_GPT4O) $(GO_GOOSE_O3) -o $@ -d comparisons/go-all

comparisons/go-opus.json:
	uv run ontoeval combine  $(GO_CLAUDECODE_SONNET) $(GO_GOOSE_SONNET) $(GO_GOOSE_GPT4O) $(GO_GOOSE_O3) $(GO_GOOSE_OPUS) -o $@ -d comparisons/go-opus

comparisons/go-gemini.json:
	uv run ontoeval combine  $(GO_GOOSE_SONNET) $(GO_GEMINI) -o $@ -d comparisons/go-gemini


comparisons/go-claudecode-v-goose.json: 
	uv run ontoeval combine $(GO_CLAUDECODE_SONNET) $(GO_GOOSE_SONNET) -o $@ -d comparisons/go-claudecode-v-goose

comparisons/go-sonnet-v-4o.json: 
	uv run ontoeval combine $(GO_GOOSE_SONNET) $(GO_GOOSE_GPT4O) -o $@ -d comparisons/go-sonnet-v-4o

comparisons/go-sonnet-v-o3.json: 
	uv run ontoeval combine $(GO_GOOSE_SONNET) $(GO_GOOSE_O3) -o $@ -d comparisons/go-sonnet-v-o3

comparisons/go-main.json: 
	uv run ontoeval combine $(GO_GOOSE_SONNET) $(GO_GOOSE_GPT4O) $(GO_GOOSE_O3) -o $@ -d comparisons/go-main


MO_BATCH_2_NOSI = experiments/mondo-3/results/results-120.json
MO_BATCH_2_WITHSI = experiments/mondo-4/results/results-120.json

comparisons/mo-si.json:
	uv run ontoeval combine  $(MO_BATCH_2_NOSI) $(MO_BATCH_2_WITHSI) -o $@ -d comparisons/mo-si

# TODO: check zero-value entries
comparisons/mo-si/heatmap.f1.png:
	linkml-store plot heatmap comparisons/mo-si/scores.csv  -y title -x experiment_id -v metadiff_judge_f1_score -o $@
comparisons/mo-si/heatmap.sd.png:
	linkml-store plot heatmap comparisons/mo-si/scores.csv  -y title -x experiment_id -v llm_judge_score_diff -o $@


UB_SON4_CC = experiments/uberon-3/results/results-180.json
UB_SON4_GS_BR = experiments/uberon-2/results/results-100.json
UB_SON4_GS = experiments/uberon-4/results/results-200.json

comparisons/ub-all.json:
	uv run ontoeval combine -c metadiff_judge_similarity $(UB_SON4_CC) $(UB_SON4_GS)   $(UB_SON4_GS_BR) -o $@ -d comparisons/ub-all

comparisons/ub-all/heatmap.f1.png:
	linkml-store plot heatmap comparisons/ub-all/scores.csv  -y title -x experiment_id -v metadiff_judge_f1_score -o $@

comparisons/ub-all/heatmap.sim.png:
	linkml-store plot heatmap comparisons/ub-all/scores.csv  -y title -x experiment_id -v metadiff_judge_similarity -o $@


MO_SON4_GS = experiments/mondo-1/results/results-100.json

comparisons/mo-all.json:
	uv run ontoeval combine -c metadiff_judge_similarity $(MO_SON4_GS) -o $@ -d comparisons/mo-all

comparisons/mo-all/heatmap.f1.png:
	linkml-store plot heatmap comparisons/mo-all/scores.csv  -y title -x experiment_id -v metadiff_judge_f1_score -o $@

comparisons/mo-all/heatmap.sim.png:
	linkml-store plot heatmap comparisons/mo-all/scores.csv  -y title -x experiment_id -v metadiff_judge_similarity -o $@

FB_SON4_GS = experiments/fb-1/results/results-80.json

comparisons/fb-all.json:
	uv run ontoeval combine -c metadiff_judge_similarity $(FB_SON4_GS) -o $@ -d comparisons/fb-all

comparisons/fb-all/heatmap.f1.png:
	linkml-store plot heatmap comparisons/fb-all/scores.csv  -y title -x experiment_id -v metadiff_judge_f1_score -o $@

comparisons/fb-all/heatmap.sim.png:
	linkml-store plot heatmap comparisons/fb-all/scores.csv  -y title -x experiment_id -v metadiff_judge_similarity -o $@

# evals

# run this first
experiments/evals/ub.json:
	uv run ontoeval create-eval -c experiments/uberon-3.yaml $(UB_SON4_CC) -o $@ -l 6

test-submit:
	uv run ontoeval submit-eval experiments/evals/ub.json --dataset-name uberon-test5 -C

test-q:
	 uv run ontoeval query-eval --dataset-name uberon-test4 experiments/evals/ub.json -o $@

# sync best

UB_BEST = $(UB_SON4_CC)
GO_BEST = $(GO_GOOSE_SONNET)
MO_BEST = $(MO_BATCH_2_WITHSI)
FB_BEST = $(FB_SON4_GS)
sync-best:
	cp $(UB_BEST) experiments/collated/uberon/results.json
	cp $(GO_BEST) experiments/collated/go/results.json
	cp $(MO_BEST) experiments/collated/mondo/results.json
	cp $(FB_BEST) experiments/collated/fb/results.json

sync-dirs:
	cp -pr $(dir $(UB_BEST))/{markdown,json} experiments/collated/uberon/
	cp -pr $(dir $(GO_BEST))/{markdown,json} experiments/collated/go/
	cp -pr $(dir $(MO_BEST))/{markdown,json} experiments/collated/mondo/
	cp -pr $(dir $(FB_BEST))/{markdown,json} experiments/collated/fb/

all-best: experiments/collated/uberon/results.all experiments/collated/go/results.all experiments/collated/mondo/results.all experiments/collated/fb/results.all





# PR Stats


prs/go-%.json:
	$(RUN) ontoeval analyze geneontology/go-ontology $* -o $@

stats/go-prs-limit-%.json:
	$(RUN) ontoeval batch geneontology/go-ontology -l $* -o $@
.PRECIOUS: stats/go-prs-limit-%.json

stats/uberon-prs-limit-%.json:
	$(RUN) ontoeval batch obophenotype/uberon -l $* -o $@
.PRECIOUS: stats/uberon-prs-limit-%.json

stats/mondo-prs-limit-%.json:
	$(RUN) ontoeval batch monarch-initiative/mondo -l $* -o $@
.PRECIOUS: stats/mondo-prs-limit-%.json

stats/po-prs-limit-%.json:
	$(RUN) ontoeval batch Planteome/plant-ontology -l $* -o $@
.PRECIOUS: stats/po-prs-limit-%.json

stats/fbbt-prs-limit-%.json:
	$(RUN) ontoeval batch FlyBase/drosophila-anatomy-developmental-ontology -l $* -o $@
.PRECIOUS: stats/fbbt-prs-limit-%.json


# Generic

stats/%.duckdb: stats/%.json
	shep -d $@ -c main insert -J benchmarks $<

stats/%.xlsx: stats/%.duckdb
	shep -d $< $(Q)  -o $@ -O xlsx

stats/%.tsv: stats/%.duckdb
	shep -d $< $(Q) -o $@ -O tsv

stats/%.jsonl: stats/%.duckdb
	shep -d $< $(Q) -o $@ -O jsonl

stats/%.fq.yaml: stats/%.duckdb
	shep -d $< fq -O yaml -o $@

stats/%.fq.png: stats/%.duckdb
	shep -d $< fq -O png -o $@

stats/comments-%.json: stats/%.json
	uv run ontoeval extract-comments $< -o $@

stats/comments-%.bar.png: stats/comments-%.json
	linkml-store plot barchart -x author $< -w 40 -h 40 -o $@

stats/%.hist.diff-size.png: stats/%.jsonl
	shep plot histogram -b 100 --y-log-scale $< -x diff_size_lines -o $@

stats/%.barchart.a.png: stats/%.jsonl
	shep plot barchart  $< -x author -o $@

stats/%.lineplot.a.png: stats/%.jsonl
	shep plot lineplot -p M  $< -x created_at -g author -m 50 -o $@

stats/%.boxplot.ad.png: stats/%.jsonl
	shep plot boxplot  $< -x diff_size_lines -y author -o $@

stats/%.heatmap.af.png: stats/%.jsonl
	shep plot heatmap --cluster both -f jsonl $< -x files_changed -y author -o $@

stats/%.heatmap.al.png: stats/%.jsonl
	shep plot heatmap --cluster both -f jsonl $< -x issue_labels -y author -o $@

stats/%.all:  stats/%.heatmap.al.png stats/%.heatmap.af.png  stats/%.boxplot.ad.png stats/%.barchart.a.png stats/%.hist.diff-size.png
	echo done



# repo cloning
# ensure no-remote: no test data leakage, no communication on tickets

workdir/go-ontology:
	cd workdir && git clone --no-remote https://github.com/geneontology/go-ontology.git && cd go-ontology && rm -rf CLAUDE.md .claude .settings

workdir/obi:
	cd workdir && git clone --no-remote https://github.com/obi-ontology/obi.git
workdir/uberon:
	cd workdir && git clone --no-remote https://github.com/obophenotype/uberon.git
workdir/mondo:
	cd workdir && git clone --no-remote https://github.com/monarch-initiative/mondo.git  && cd mondo && rm -rf CLAUDE.md .goosehints .claude .settings

workdir/fbbt:
	cd workdir && git clone --no-remote https://github.com/FlyBase/drosophila-anatomy-developmental-ontology.git

workdir/plant-ontology:
	cd workdir && git clone --no-remote https://github.com/Planteome/plant-ontology.git
