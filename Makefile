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

experiments/go-goose-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-1.yaml -I src/ontology/go-edit.obo -o $@ -l $*
.PRECIOUS: experiments/go-goose-1/results/results-%.json

experiments/go-goose-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-2.yaml -I src/ontology/go-edit.obo -o $@ -l $*
.PRECIOUS: experiments/go-goose-2/results/results-%.json

experiments/go-goose-3/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-3.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-3/results/markdown  -l $*
.PRECIOUS: experiments/go-goose-3/results/results-%.json

experiments/go-goose-4/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-4.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-4/results/markdown  -l $*
.PRECIOUS: experiments/go-goose-4/results/results-%.json

experiments/go-goose-5/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/go-goose-5.yaml -I src/ontology/go-edit.obo -o $@  --markdown-directory experiments/go-goose-5/results/markdown  -l $*
.PRECIOUS: experiments/go-goose-5/results/results-%.json

experiments/uberon-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-1.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-1/results/markdown  -l $*
.PRECIOUS: experiments/uberon-1/results/results-%.json

experiments/uberon-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/uberon-2.yaml -I src/ontology/uberon-edit.obo -o $@ --markdown-directory experiments/uberon-2/results/markdown  -l $*
.PRECIOUS: experiments/uberon-2/results/results-%.json

experiments/mondo-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-1.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-1/results/markdown  -l $*
.PRECIOUS: experiments/mondo-1/results/results-%.json

experiments/mondo-2/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/mondo-2.yaml -I src/ontology/mondo-edit.obo -o $@ --markdown-directory experiments/mondo-2/results/markdown  -l $*
.PRECIOUS: experiments/mondo-2/results/results-%.json


experiments/po-1/results/results-%.json:
	time $(RUN) ontoeval run-all -c experiments/po-1.yaml -I plant-ontology.obo -o $@ -l $*
.PRECIOUS: experiments/po-1/results/results-%.json

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

experiments/%.hist.sim.png: experiments/%.jsonl
	shep plot histogram -b 20  $< -x metadiff_judge_similarity -o $@

experiments/%.hist.sim2.png: experiments/%.jsonl
	shep plot histogram -b 20  $< -x llm_judge_similarity -o $@

experiments/%.scatter.sd.png: experiments/%.jsonl
	shep plot scatterplot  $< -x llm_judge_difficulty -y llm_judge_score_diff -o $@

experiments/%.scatter.ss.png: experiments/%.jsonl
	shep plot scatterplot  $< -x llm_judge_similarity -y metadiff_judge_similarity -o $@


# PR Stats


prs/go-%.json:
	$(RUN) ontoeval analyze geneontology/go-ontology $* -o $@

stats/go-prs-limit-%.json:
	$(RUN) ontoeval batch geneontology/go-ontology -l $* -o $@
.PRECIOUS: stats/go-prs-limit-%.json

stats/uberon-prs-limit-%.json:
	$(RUN) ontoeval batch obophenotype/uberon -l $* -o $@
.PRECIOUS: stats/uberon-prs-limit-%.json

stats/po-prs-limit-%.json:
	$(RUN) ontoeval batch Planteome/plant-ontology -l $* -o $@
.PRECIOUS: stats/po-prs-limit-%.json

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

stats/%.hist.diff-size.png: stats/%.jsonl
	shep plot histogram -b 100 --y-log-scale $< -x diff_size_lines -o $@

stats/%.barchart.a.png: stats/%.jsonl
	shep plot barchart  $< -x author -o $@

stats/%.lineplot.a.png: stats/%.jsonl
	shep plot lineplot  $< -x created_at -g author -o $@

stats/%.boxplot.ad.png: stats/%.jsonl
	shep plot boxplot --x-log-scale $< -x diff_size_lines -y author -o $@

stats/%.heatmap.af.png: stats/%.jsonl
	shep plot heatmap --cluster both -f jsonl $< -x files_changed -y author -o $@

stats/%.heatmap.al.png: stats/%.jsonl
	shep plot heatmap --cluster both -f jsonl $< -x issue_labels -y author -o $@



# repo cloning
# ensure no-remote: no test data leakage, no communication on tickets

workdir/go-ontology:
	cd workdir && git clone --no-remote https://github.com/geneontology/go-ontology.git

workdir/obi:
	cd workdir && git clone --no-remote https://github.com/obi-ontology/obi.git
workdir/uberon:
	cd workdir && git clone --no-remote https://github.com/obophenotype/uberon.git
workdir/mondo:
	cd workdir && git clone --no-remote https://github.com/monarch-initiative/mondo.git

workdir/plant-ontology:
	cd workdir && git clone --no-remote https://github.com/Planteome/plant-ontology.git
