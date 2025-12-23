# Analysis Script — Summary

This analysis module computes team- and PR-level summary statistics from the CSV artifacts produced by the extractor and enrichment pipeline. It expects team folders under `data/csv/` following the `year-long-project-team-*` pattern and looks for the standard CSVs the pipeline produces (pull requests, commits, commit_file_changes, review-comments).

## Quick setup

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Expected input layout

The analysis script expects the common pipeline filenames inside each team folder, for example:

```
data/csv/year-long-project-team-1/
  ├─ year-long-project-team-1_all_pull_requests.csv
  ├─ year-long-project-team-1_PR_commits.csv
  ├─ year-long-project-team-1_commit_file_changes.csv
  └─ year-long-project-team-1_review-comments.csv
```

## Metrics and outputs

Typical metrics produced by the analysis include:

- Number of branches, PRs, commits, files modified
- Lines of code added/deleted
- Reviews and comments counts
- Merges and related statistics

The script aggregates these into team-level rows and generates project-level summaries (means and standard deviations) and PR-level averages. Outputs are saved under `data/analysis/` (for example `table2_statistics.csv`, `team_level_data.csv`, `extreme_teams.csv`).

## Notes

- The analysis module is flexible with column names (it includes mapping utilities to support variations such as `lines_added` vs `additions`).
- If a team folder is missing required files, it will be skipped with a warning and processing will continue for other teams.
- This module is intended to consume cleaned/enriched CSVs created by the extraction and labeling pipeline.

## Notes specific to `analysis.py`

- `analysis.py` writes outputs into `data/analysis/` (the script creates the folder if it doesn't exist).
- The script contains utilities to normalize column name variations and will try common alternatives
  for `lines_added`, `lines_deleted` and `files_changed` — this makes it resilient to small
  differences in extractor output.
- If `data/csv/` has no team folders matching `year-long-project-team-*` the script will raise a
  `FileNotFoundError`; for incremental work you can comment that check or point `DATA_FOLDER` to a
  subset folder for local testing.
