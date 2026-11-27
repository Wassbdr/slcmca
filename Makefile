# slacheck: reproducibility and quality targets.
# No Datadog credentials required. Thin wrappers over the scripts and the
# CLI so the paper's numbers, figures, and checks are one command each. See docs/paper_mapping.md.

PY ?= python

.PHONY: help check test lint types eval bench bench-tools docs showcase figures reproduce paper clean-paper

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

check: lint types test  ## Lint + type-check + tests (the full quality gate)

test:  ## Run the offline test suite (live tests skipped by default)
	pytest

lint:  ## Ruff lint
	ruff check .

types:  ## mypy type-check
	mypy

eval:  ## Print Table I (tab:eval) as LaTeX, regenerated from the code
	$(PY) -m slacheck.cli eval --both --latex

bench:  ## Compare topology checks and any installed reference tools
	$(PY) -m scripts.bench

bench-tools:  ## Download and verify pinned reference binaries for Linux x86-64
	$(PY) -m scripts.bench_tools

docs:  ## Build the documentation with link checks
	$(PY) -m mkdocs build --strict

showcase:  ## Rebuild showcase media and results
	bash showcase/make_showcase.sh

reproduce:  ## Reproduce every paper number + figure offline (datasets -> tables -> figures)
	$(PY) scripts/reproduce_paper.py

figures:  ## Regenerate figures/*.pdf from the evaluation code paths
	$(PY) scripts/gen_figures.py

paper: issre_paper.pdf  ## Compile issre_paper.tex (needs a LaTeX toolchain)

issre_paper.pdf: issre_paper.tex refs.bib $(wildcard figures/*.pdf)
	pdflatex -interaction=nonstopmode issre_paper.tex
	bibtex issre_paper
	pdflatex -interaction=nonstopmode issre_paper.tex
	pdflatex -interaction=nonstopmode issre_paper.tex

clean-paper:  ## Remove LaTeX build artifacts (keeps issre_paper.pdf)
	rm -f issre_paper.aux issre_paper.bbl issre_paper.blg issre_paper.log \
		issre_paper.out issre_paper.toc issre_paper.synctex.gz
