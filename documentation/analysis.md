# Analysis Script — Summary

This document explains what `analysis.py` does and how to run it. The script computes team-level and PR-level summary statistics from CSV artifacts produced by the extraction and enrichment pipeline. It is intended to be run from the repository root and expects per-team folders under `data/csv/` that follow the `year-long-project-team-*` pattern.

## Requirements

- Python 3.8+ (project uses standard data-science libraries)
- Key packages: `pandas`, `numpy` (install via `pip install -r requirements.txt`)

## How to run

From the project root:

```bash
python analysis.py
```

The script creates `data/analysis/` and writes CSV outputs there. It prints progress to console and displays summary statistics at the end.

## What the script expects (inputs)

`analysis.py` looks for team folders matching the glob `data/csv/year-long-project-team-*`. Inside each team folder it tries to locate common CSVs using flexible filename patterns:

**Pull requests CSV** (tries these patterns in order):
- `{team}_all_pull_requests.csv`, `{team}_PRs.csv`, `all_pull_requests.csv`, `pull_requests.csv`

**Commits CSV** (tries these patterns):
- `{team}_PR_commits.csv`, `{team}_commits.csv`, `PR_commits.csv`, `commits.csv`

**Commit file changes CSV** (tries these patterns):
- `{team}_commit_file_changes.csv`, `{team}_file_changes.csv`, `commit_file_changes.csv`, `file_changes.csv`

**Review/comments CSV** (tries these patterns):
- `{team}_review-comments.csv`, `review-comments.csv`, `reviews.csv`

If a required PR file is missing for a team, the script logs a warning and skips that team. Other files are optional (if missing, that metric will be zero).

## What the script computes (metrics)

Per-team statistics collected from each CSV include:

- **Number of branches** — counts unique values in `head_branch` column
- **Number of PRs** — row count of PR CSV
- **Number of commits** — row count of commits CSV
- **Number of files** — counts unique values in `file_path` column (from file changes)
- **Lines of code** — sum of `lines_added` and `lines_deleted` (tries common column name variations)
- **Number of reviews** — row count of reviews CSV
- **Number of comments** — counts non-null values in comment body columns
- **Number of merges** — counts non-null values in `merged_at` column

The script aggregates these per-team values to produce:
- **Project-level statistics**: mean and standard deviation across all teams
- **PR-level statistics**: per-PR averages (total metric ÷ number of PRs per team)

## Outputs

Files written to `data/analysis/`:

1. **`table2_statistics.csv`** — summary table with columns:
   - `Characteristic` (metric name)
   - `Project Statistics` (mean and std for all teams)
   - `PR Statistics` (per-PR mean and std, where applicable)

2. **`team_level_data.csv`** — per-team rows with all computed metrics (one row per team)

3. **`extreme_teams.csv`** — identifies most/least productive teams (ranked by lines of code)

Console output also displays these tables and highlights the extreme teams.

## Robustness & configuration notes

- **Column name flexibility**: Helper functions like `normalize_column_name()` and `safe_sum_column()` look for common variations. For example, the script will accept either `lines_added` or `additions` as column names.
- **Path configuration**: The script sets `ROOT` relative to its own file location. If you run it from a different working directory or embed it in another workflow, ensure `DATA_FOLDER` and `OUTPUT_FOLDER` point to the correct locations.
- **Error handling**: If no team folders are found, the script raises `FileNotFoundError` with a clear message. If a team folder is missing CSVs, that team is skipped with a warning printed to console.
- **Missing metrics**: If a CSV is missing (e.g., no file changes data), that metric will be zero for affected teams.

## Quick troubleshooting

**No outputs / FileNotFoundError:**
- Verify `data/csv/` exists and contains folders matching the pattern `year-long-project-team-*`
- Ensure you're running from the repository root: `pwd` should show `/...pathto.../processAnalysis`

**Zero or incorrect line counts:**
- Check whether PR CSVs or file changes CSVs have `lines_added` or `additions` columns
- The script will try both; if neither exists, line counts will be zero
- Check console output for which files were actually loaded

**Single-team debugging:**
- Temporarily comment out the `FileNotFoundError` check and modify `team_folders` to a single folder
- Or point `DATA_FOLDER` to a test subfolder containing a single team folder

**Column name mismatches:**
- Review the `COLUMN_MAPPINGS` dictionary at the top of `analysis.py`
- Add more alternatives if your CSVs use non-standard column names

## Next steps

- Run the script on your full dataset to generate baseline statistics
- Use `team_level_data.csv` to inspect individual team contributions
- Use `extreme_teams.csv` to identify outlier teams (most/least productive)
