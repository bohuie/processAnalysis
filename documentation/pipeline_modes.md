# Pipeline Modes

This document clarifies the two supported pipeline entrypoints and when to use each one.

## Mode 1: Full Pipeline

Entrypoint: `main.py`

What it does:
1. Extracts GitHub data (PRs, commits, files, reviews) into `data/csv/<repo-name>/`
2. Runs code-structure and PR labeling
3. Runs process-model generation (transition edges, z-scores, clustering, graphing)
4. Runs team-level analysis (`analysis.py`)

Use this mode when:
- You need fresh extraction from GitHub
- You changed the repository owner or repository names in `main.py` / `scripts/app.py`
- You want a complete end-to-end run

Local run:

```bash
python main.py
```

To target a different dataset, update the hardcoded `repos` list and repository owner in `main.py`, and update `scripts/app.py` if you run extraction separately.

## Mode 2: Process-Only Pipeline

Entrypoint: `process_model_only.py`

What it does:
1. Skips extraction
2. Uses existing files in `data/csv/`
3. Runs labeling + process models + analysis

Use this mode when:
- Extraction is already complete
- You are iterating on labeling/model code
- You want a faster rerun without GitHub API calls

Local run:

```bash
python process_model_only.py
```

Docker run:

```bash
docker-compose -f docker-compose.process.yml run --rm process python process_model_only.py
```

The helper script [run-docker-process.sh](../run-docker-process.sh) currently runs this mode by default.

## Environment Variables

Common variables:
- `GITHUB_TOKEN` (required for extraction in full mode)
- `AI_MODE` (`offline` or `online`)
- `GROQ_API_KEY` (required only when `AI_MODE=online`)

Repository owner and repository names are configured in code:
- `main.py` for the full pipeline
- `scripts/app.py` for extraction-only runs

## Prevent Mixed Old/New Outputs

If you switch datasets (for example from year-long repos to a different org), clear previously generated artifacts before rerunning full mode.

Suggested cleanup:

```bash
rm -rf data/outputs/*
rm -rf data/graph_labels/clean/*
rm -f data/csv/CLEAN_pr_labels_*.csv
rm -f data/csv/CLEAN_communication_labels_*.csv
```

Then rerun full mode.

## Quick Decision Guide

- Need fresh GitHub pull? Use `main.py`.
- Already have extraction and just need modeling? Use `process_model_only.py`.
- Running `run-docker-process.sh`? It currently executes full mode (`main.py`).
