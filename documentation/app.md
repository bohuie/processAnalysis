# Main Data Extraction Script — Notes

This document describes the project's GitHub extraction tooling and the common filenames the rest of the pipeline expects. The actual implementation lives in `src/extractors` (see `PullRequestExtractor`) and in scripts that call it.

## Overview

The extractor fetches pull requests, associated commits, file-level changes and review comments and writes CSV/JSON artifacts used by downstream labeling scripts.

## Features

- Pull request extraction with pagination and rate-limit handling
- Commit and file-change tracking per PR
- Review comment extraction with fallback mechanisms
- Orphan commit detection (commits not associated with any PR)
- CSV and JSON export (configurable)

## Prerequisites

- Python 3.8+
- A GitHub personal access token for higher rate limits (recommended)
- Install dependencies from the repository requirements:

```bash
python -m pip install -r requirements.txt
```

Create a `.env` with `GITHUB_TOKEN` if you want authenticated requests.

## Configuration

Typical parameters used by wrappers around the extractor:

- `repo_owner` — repository owner/organization
- `repo_name` — target repository name
- `output_base_dir` — output base directory (default: `./data`)
- `save_json` / `save_csv` — booleans to control output formats
- `include_orphan_commits` — include commits not associated with PRs

## Output files & naming conventions

The rest of the processing pipeline expects CSVs using the following naming patterns inside each team's folder under `data/csv/{team_folder}`:

- `{team_name}_all_pull_requests.csv`
- `{team_name}_PR_commits.csv` (or a commits file)
- `{team_name}_commit_file_changes.csv` (file-level changes, used for size/refactor metrics)
- `{team_name}_review-comments.csv`

The extractor should write these files into `data/csv/{repo_folder}/` so downstream scripts can discover them using the `year-long-project-team-*` pattern.

## Usage (example)

Run a small wrapper script or import the extractor class from `src.extractors`:

```python
from src.extractors.pull_request_extractor import PullRequestExtractor

extractor = PullRequestExtractor(repo_owner='your-org', repo_name='your-repo', need_auth=True)
extractor.run(save_csv=True, save_json=False, include_orphan_commits=True)
```

## Notes specific to `scripts/app.py`

- The main wrapper script for extraction is `scripts/app.py`. When run it prints a debug
	`Project root` line and early import diagnostics — useful when adjusting Python path issues.
- `scripts/app.py` contains helper functions that enrich PR rows before writing CSVs; the
	CSV fieldnames written by the helper are listed in the source (for example: `pr_id`,
	`created_at`, `pr_author`, `pr_title`, `pr_description`, `merged_by`, `was_up_to_date_at_merge`,
	`docs_updated`, `lines_added`, `lines_deleted`, `files_changed`).

## Notes

- Ensure the generated filenames match the pipeline naming scheme above.
- The extractor supports optional README/log exclusion settings used to filter out log-only PRs.
- For large repositories, use an authenticated token to reduce rate limiting.
