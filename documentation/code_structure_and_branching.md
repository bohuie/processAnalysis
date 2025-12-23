# Code Structure & Branching — Script Reference

This document reflects the current behaviour of `event_labelling/CodeStructure_Branching/code_structure_and_branching.py` (refactor branch). It describes inputs, configuration, main processing steps, and outputs produced by `process_all_teams()`.

## Summary

- Cleans review comments (extracts usernames from dict-like fields)
- Enriches PRs with top-file metrics and a docs-updated flag
- Adds `order_of_review` to review comments
- Removes bot PRs/commits using utilities in `src.utils.botFilter`
- Optionally anonymizes authors and branch-name username components
- Generates event labels (branch naming, feature/refactor sizes, repo/pr/merge status)
- Saves labels and LLM reasoning to `data/graph_labels/`

## Key Requirements

- Python 3.8+ (project uses `pyenv` in development)
- Core dependencies: `pandas`, `tqdm`, `python-dateutil` (see `requirements.txt`)
- Local Ollama instance for LLM assessments (optional if `connect_ollama_offline` is a no-op)

Quick install (example):
```bash
python -m pip install -r requirements.txt
# If you use Ollama locally:
# ollama serve
# ollama pull llama3.2:3b
```

## Where to run

Run the script from the project root (repository root is assumed):

```bash
python event_labelling/CodeStructure_Branching/code_structure_and_branching.py
```

## Directory expectations

The script expects team CSV folders under `data/csv/` using the pattern `year-long-project-team-*`.

Example structure:

```
data/csv/
└── year-long-project-team-1/
   ├── year-long-project-team-1_all_pull_requests.csv
   ├── year-long-project-team-1_PR_commits.csv
   ├── year-long-project-team-1_commit_file_changes.csv
   └── year-long-project-team-1_review-comments.csv
```

An anonymization mapping (optional) is loaded from `confidential/anonymized_usernames.json` relative to the project root. If present, the `ANONYMIZE` global flag controls whether anonymization is applied.

## Main Configuration (script-level)

Key module-level constants in the script:

- `MODEL_NAME` — LLM model identifier used by the local `ask_llm` wrapper (default: `llama3.2:3b`)
- `RUN_TIMESTAMP` — ISO timestamp used in label outputs
- `ANONYMIZE` — boolean flag to enable anonymization

The code uses the helper `connect_ollama_offline` from `src.utils.ollama_offline` for LLM calls.

## Processing stages (what the script does)

1. Discover all team folders under `data/csv/`.
2. For each team: run `clean_review_comments(team_folder)` to extract usernames from `author` fields in review comments and overwrite the CSV with cleaned author values.
3. Run `enrich_prs_and_comments(team_folder)`, which delegates enrichment to utility functions in `src.utils.enrich_columns`:

   - `add_top_file_metrics(team_folder)` — computes `top_file` and `top_file_change_%` on PR CSVs
   - `add_docs_updated_flag(team_folder)` — sets `docs_updated` if docs changed
   - `add_order_of_review(team_folder)` — adds `order_of_review` to review comments

4. Load required CSVs (`*_all_pull_requests.csv`, `*_PR_commits.csv`, `*_commit_file_changes.csv`), filter bots using `src.utils.botFilter`, optionally anonymize, and prepare timestamp lookups.

5. Generate labels via functions in the same file:

   - `label_branch_names(prs_df)` — LLM-based branch-name assessment (uses `assess_branch_meaningfulness`)
   - `label_features_per_branch(prs_df)` — counts PRs per branch
   - `label_feature_size(commit_file_changes_df, prs_df, pr_created_at_lookup)` — net-new lines per commit
   - `label_refactor_size(commit_file_changes_df, prs_df, pr_created_at_lookup)` — lines modified per file
   - `label_repo_status(prs_df)` — up-to-date / outdated based on `was_up_to_date_at_merge`
   - `label_pr_status(prs_df)` — closed / still_open
   - `label_merge_state(prs_df)` — delegated to `src.utils.label_merge.label_merge_state`
6. Concatenate label DataFrames, sort, run `diagnose_timestamp_issues()` and save outputs.

## Outputs

The script writes per-team outputs to `data/graph_labels/`:

- `{team_name}_labels_branching_and_structure.csv` — combined labels for that team
- `{team_name}_llm_branch_name_reasoning.csv` — LLM reasoning rows produced from branch-name assessments

Example columns in the combined labels file:

```csv
pr_id,pr_author,created_at,branch_name,event,main_label,llm_output,llm_timestamp
```

Notes:

- `clean_review_comments()` overwrites `*_review-comments.csv` files in-place after extraction of usernames.
- The anonymization mapping (if present) is loaded from `confidential/anonymized_usernames.json` in the project root and applied with case-insensitive replacement across selected columns (`pr_author`, `merged_by`, `head_branch`).
- Bot filtering and anonymization are performed using utilities from `src.utils`.

## LLM behavior and parsing

- Branch naming assessments are performed by `assess_branch_meaningfulness()` which sends a formatted prompt to `ask_llm`. The function attempts to parse `REASON`, `PREDICTION` and `CONFIDENCE` sections from the model output and falls back to defaults when parsing fails.

## Notes on running and debugging

- Run the script from the repository root so the relative paths resolve correctly.
- If you do not run an Ollama instance, ensure `connect_ollama_offline` is implemented to either mock responses or fail gracefully.
- If files are missing in a team folder, the team is skipped with a warning.

## Functions referenced (high-level)

- `clean_review_comments(team_folder)` — extract usernames from review comments and normalize formatting
- `enrich_prs_and_comments(team_folder)` — delegates enrichment to utilities in `src.utils.enrich_columns`
- `label_branch_names(prs_df)` — LLM-based branch-name labeling
- `label_features_per_branch(prs_df)` — features per branch
- `label_feature_size(...)`, `label_refactor_size(...)` — code/feature size heuristics
- `label_repo_status(prs_df)`, `label_pr_status(prs_df)` — repo and PR status labels
- `process_all_teams()` — main orchestration function
