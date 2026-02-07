# PR Labeling

This document describes the **PR labeling system** in `event_labelling/PR/`. The tooling processes extracted GitHub pull request data (PRs, commits, and review comments) to generate **PR labels** used for research on review quality, merge practices, and documentation clarity.

Primary entry point: `event_labelling/PR/pr_label.py` (run as a module).

---

## Overview & Purpose

The PR labeler generates event labels that answer questions like:

- **How were PRs merged?** (self-merge vs reviewed merge vs no-merge)
- **Were reviews constructive?** (constructive vs non-constructive, and which review round)
- **Did reviewers request changes?**
- **Are PR descriptions clear enough to be useful?**
- **Are there low-signal “empty” approvals?**

These labels are used downstream as timestamped events for analysis and graph-based modeling.

---

## Summary of What the Script Does

For each team folder in `data/csv/year-long-project-team-*`, the pipeline:

1. **Discovers team CSVs** using flexible filename patterns.
2. **Preprocesses raw CSVs** (bot filtering, “log PR” filtering, review-specific cleanup, `order_of_review`, anonymization) into `CLEAN_*.csv` files.
3. **Normalizes PR IDs** across PR/commit/review tables.
4. **Builds timestamp lookups** (PR timestamps; review comment timestamps).
5. **Labels merge state** (`self_merge`, `reviewed_merge`, `no_merge`).
6. **Labels review attributes** (changes requested, empty approvals, and LLM-based constructiveness).
7. **Labels PR description clarity** using a word-count heuristic.
8. **Combines + filters** to a PR-only label CSV per team.
9. **Produces a “clean” three-column CSV** (`pr_id`, `timestamp`, `event`) for event graph ingestion.

Implementation lives mainly in:

- `pr_label.py` (orchestrator)
- `prep_data.py` (preprocessing)
- `review_helper.py` (review constructiveness + review attributes)
- `llm_prompts.py` (constructiveness prompt + PR description labeler)
- `helpers_pr.py` (bot filtering helpers + log PR detection helpers)
- `process_model/clean.py` (imported) — Handles final event cleaning and timestamp selection for graph ingestion.

---

## Key Requirements

- **Python**: 3.8+
- **Core dependencies**: `pandas`, `numpy`, `tqdm`, `python-dotenv`
- **LLM backend**: This PR pipeline’s constructiveness classifier calls a **Groq-backed LLM client** via `src.utils.connect_groq`. You’ll typically need an API key in your environment / `.env`.

---

## Running the Script

Run from the **repo root** so relative paths resolve correctly:

```bash
python -m event_labelling.PR.pr_label
```

This will process every folder matching:

```
data/csv/year-long-project-team-*
```

and write outputs back into `data/csv/`.

---

## Input Data Expectations

### Folder layout

Each team has its own folder under `data/csv/`:

```
data/csv/year-long-project-team-1/
├── year-long-project-team-1_all_pull_requests.csv   (or *_PRs.csv, etc.)
├── year-long-project-team-1_PR_commits.csv          (or *_commits.csv, etc.)
└── year-long-project-team-1_review-comments.csv     (or review-comments.csv)
```

The script searches for multiple acceptable filenames via templates in `PRS_PATTERN_TEMPLATES`, `COMMITS_PATTERN_TEMPLATES`, and `REVIEWS_PATTERN_TEMPLATES`.

### Required columns (minimum)

**PRs CSV** should include (at least):

- `pr_id`
- `created_at`
- merge-related fields needed by `label_merge_state` (often includes `merged_at`, merge status info)
- `pr_author` (if absent, defaults to `"unknown"`)

**Review-comments CSV** should include (at least):

- `pr_id`
- `author`, `pr_author`
- `comment_type` (expects values like `"review"`, `"inline"`, `"conversation"`)
- `comment_body`
- `state` (e.g., `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`)
- `created_at` and/or `comment_id` (if `comment_id` exists, it builds a comment timestamp lookup)

**Output PR label CSV** (the one this pipeline writes) must include:

- `pr_id`, `event`, `created_at`, `updated_at`, `merged_at`
  because the “clean” exporter requires them.

---

## Configuration

Most behavior is encoded in code-level constants inside `pr_label.py`:

### Filename discovery patterns

- `PRS_PATTERN_TEMPLATES`
- `COMMITS_PATTERN_TEMPLATES`
- `REVIEWS_PATTERN_TEMPLATES`

### Allowed PR event labels

`PR_LABELS` is the whitelist of labels that make it into the final `pr_labels_{team}.csv`:

- `self_merge`
- `reviewed_merge`
- `no_merge`
- `constructive_first_review`, `constructive_second_review`, `constructive_additional_review`
- `non_constructive_first_review`, `non_constructive_second_review`, `non_constructive_additional_review`
- `pr_description_clear`, `pr_description_unclear`
- `changes_requested`
- `approved_empty_review`

---

## Processing Pipeline (Detailed)

### Stage 1: Team discovery + CSV selection

- Scans for team folders:
  - `glob(data/csv/year-long-project-team-*)`

- Locates PR/commit/review CSVs using `find_file(folder, patterns)` across multiple allowed names.

If any required file is missing for a team, that team is skipped.

---

### Stage 2: Preprocessing (writes `CLEAN_*.csv`, does not overwrite originals)

Preprocessing is performed by `preprocess_team_csvs(...)` in `prep_data.py`.

It applies:

#### (A) Bot filtering

Drops rows where any _author-like_ column is a bot account (PRs, commits, reviews).

#### (B) “Log PR” filtering (global drop across all sources)

Detects PR IDs where **any row** contains “logs / weeklylogs / teamlogs / personallogs” in any non-`pr_id` column, then drops those PR IDs from PRs, commits, and reviews.

#### (C) Review-specific filters

Applied only to the reviews table:

1. Remove rows where `author == pr_author` (self-review removal).
2. Remove “empty COMMENTED reviews”: `comment_type == review` AND empty `comment_body` AND `state == COMMENTED`.
3. Remove `comment_type == conversation` rows.

#### (D) Add `order_of_review`

Calls `add_order_of_review(team_folder)` (from `src.utils.enrich_columns`) to add an ordinal review sequence column used later for “first/second/additional review” labels.

#### (E) Anonymize author columns

Calls `anonymize_author_columns(...)` (from `src.utils.anonymize_columns`) on the CLEAN files.

> Result: three files are produced (and used for the rest of the pipeline):
>
> - `CLEAN_<prs_file>.csv`
> - `CLEAN_<commits_file>.csv`
> - `CLEAN_<review-comments_file>.csv`

---

### Stage 3: Timestamp lookups

The orchestrator builds and saves:

- `data/csv/pr_timestamp_lookup.csv` mapping `pr_id → created_at`
- `data/csv/review_timestamp_lookup.csv` mapping `comment_id → created_at` (only if `comment_id` exists)

These are used to backfill missing `created_at` on review rows during labeling.

---

### Stage 4: Merge state labeling

`label_merge_state(prs_df)` is called (from `src.utils.label_merge`) and its per-PR `event` result is appended into `prs_df["event"]`.

This produces PR-level merge labels that the rest of the pipeline treats specially for timestamps later:

- Merge events: `reviewed_merge`, `self_merge`
- Non-merge event: `no_merge`

---

### Stage 5: Review labeling (review attributes + LLM constructiveness)

Implemented in `label_review_constructiveness(...)` (in `review_helper.py`).

#### 5.1 Backfill/sanitize review metadata

- Fills missing `comment_body` with `""`
- Normalizes `state` and `comment_type` (lower/upper helper columns)
- Sets `review_author` from `author`
- Ensures `created_at` is populated (via `comment_id → created_at` lookup, then `pr_id → created_at` lookup)
- Sorts by `pr_id`, reviewer, timestamp (and `comment_id` if present)

#### 5.2 `changes_requested`

For each reviewer group, any `comment_type == review` row with `state == CHANGES_REQUESTED` gets the `changes_requested` event appended.

#### 5.3 `approved_empty_review`

If a reviewer has exactly **one** review row on that PR, and it is `APPROVED` with an empty body, label it `approved_empty_review`.

#### 5.4 Constructiveness (LLM-based)

Constructiveness is classified **once per (pr_id, review_author)** on a chosen “target” review message:

**Target selection rule:**

- If there is an `APPROVED` review:
  - Choose the **last review before the first APPROVED**, if any exist.
  - Otherwise choose the `APPROVED` itself.

- If there is **no** `APPROVED` review:
  - Choose the **last** review row.

**Context passed to the LLM:**

- The target review body (“PRIMARY REVIEW”)
- All inline comments by that reviewer on that PR
- Other review bodies by that reviewer, excluding any `APPROVED` bodies at or after the target timestamp

**LLM call:**

- `classify_constructiveness(...)` builds a structured prompt and calls `connect_groq` (aliased as `ask_llm`).

**Output labels:**
Depending on LLM response + `order_of_review`, the pipeline appends one of:

- `constructive_first_review`
- `constructive_second_review`
- `constructive_additional_review`
- `non_constructive_first_review`
- `non_constructive_second_review`
- `non_constructive_additional_review`

It also stores:

- `llm_output` (reason text)
- `llm_timestamp` (the run timestamp)

---

### Stage 6: PR description clarity labeling (heuristic)

Implemented in `label_pr_descriptions(prs_df)` in `llm_prompts.py`.

Rule:

- Use `pr_description` if present, else `body`
- Count words:
  - `>= 10` → `pr_description_clear`
  - `< 10` → `pr_description_unclear`

This produces a small PR-level label DataFrame with columns: `pr_id`, `pr_author`, `created_at`, `event`.

---

### Stage 7: Combine + filter to PR labels only

In `pr_label.py`, the pipeline concatenates:

- `commits_df` (source = `"commit"`)
- `prs_df` (source = `"pr"`)
- `reviews_df` (source = `"review"`)
- `desc_labels` (PR description events)

Then:

- Coerces and forward-fills `created_at`
- Sorts by `created_at`
- Keeps only rows whose `event` contains at least one item in `PR_LABELS`
- Serializes event lists as a string like `"['reviewed_merge']"`

---

## Outputs

Per team, the pipeline writes:

### 1) PR labels (full rows)

**Path:**

```
data/csv/pr_labels_{team_name}.csv
```

This is the main output containing original row fields (from PRs/reviews/desc label rows) plus an `event` column that is a stringified list of PR label(s).

### 2) Clean PR labels (event stream)

Generated automatically if the above file is non-empty:

**Path:**

```
data/csv/CLEAN_pr_labels_{team_name}.csv
```

Schema:

- `pr_id`
- `timestamp`
- `event` (kept exactly as stored in the original PR labels CSV, typically a stringified list)

---

## Clean CSV Timestamp Rules (Important)

The “clean” exporter (`create_clean_pr_label_csv`) chooses timestamps per row as follows:

1. Parse `event` (which is often stored as a string like `"['reviewed_merge']"`) into a list.
2. Choose timestamp column:
   - If event contains `reviewed_merge` or `self_merge` → use `merged_at`
   - Else if event contains `no_merge` → use `updated_at`
   - Else → use `created_at`

3. If the chosen timestamp is missing/invalid, fall back to `created_at`.
4. Normalize to `YYYY-MM-DDTHH:MM:SSZ` when parseable; otherwise keep the raw value.

This is designed so merge-related events line up with merge time rather than PR creation time.

---

## Label Definitions (What each PR label means)

### Merge lifecycle

- **`self_merge`**: merged by PR author (merge occurred).
- **`reviewed_merge`**: merged by someone else / after review (merge occurred).
- **`no_merge`**: PR closed/updated without merging.

### Review actions / quality

- **`changes_requested`**: reviewer submitted a CHANGES_REQUESTED review state.
- **`approved_empty_review`**: reviewer submitted a single APPROVED review with empty body (low-signal approval).
- **Constructiveness** (LLM-based, tied to `order_of_review`):
  - `constructive_first_review`, `constructive_second_review`, `constructive_additional_review`
  - `non_constructive_first_review`, `non_constructive_second_review`, `non_constructive_additional_review`

### PR description quality

- **`pr_description_clear`**: PR body/description has **≥ 10 words**.
- **`pr_description_unclear`**: PR body/description has **< 10 words**.

---

## File Structure & Roles (PR labeling)

- **`pr_label.py`** — orchestrates discovery → preprocessing → labeling → output.
- **`prep_data.py`** — creates `CLEAN_*.csv` without overwriting originals; bot/log filtering; review cleanup; adds `order_of_review`; anonymizes.
- **`review_helper.py`** — changes requested, empty approvals, and LLM-based constructiveness labeling per (PR, reviewer).
- **`llm_prompts.py`** — LLM prompt + client aliasing for constructiveness; also PR description clarity heuristic.
- **`helpers_pr.py`** — shared utilities: safe event appending, file discovery, bot filtering wrappers, and log PR detection.
- `process_model/clean.py` — converts `pr_labels_{team}.csv` → `CLEAN_pr_labels_{team}.csv` (called automatically).

---

## Common Debugging Scenarios

| Symptom                                    | Likely Cause                                              | What to check                                                                               |
| ------------------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| “No team folders found”                    | You’re not running from repo root or `data/csv/` is empty | Confirm `data/csv/year-long-project-team-*` exists.                                         |
| Team is skipped with “Missing files”       | Filenames don’t match the template list                   | Compare your CSV filenames to the patterns in `*_PATTERN_TEMPLATES`.                        |
| No constructiveness labels                 | Review bodies are empty OR LLM isn’t configured           | Check that review `comment_body` is present; confirm Groq credentials/`connect_groq` works. |
| Too many rows removed during preprocessing | Log PR detection is broad across all columns              | Inspect which PRs contain “logs/weeklylogs/teamlogs/personallogs” in any field.             |
| CLEAN PR labels fail with missing columns  | `pr_labels_{team}.csv` lacks required timestamp columns   | Clean exporter requires `created_at`, `updated_at`, `merged_at`, `event`, `pr_id`.          |

---

## Notes / Implementation Details Worth Knowing

- **Events are stored as lists during processing**, but saved as a **stringified list** in the final PR labels file (e.g., `"['changes_requested']"`). The clean exporter re-parses that string safely.
- **Constructiveness labeling only applies to `comment_type == 'review'` rows**; inline comments are used as evidence/context but are not directly labeled.
- **“First/Second/Additional”** is determined using the `order_of_review` column added during preprocessing.

---
