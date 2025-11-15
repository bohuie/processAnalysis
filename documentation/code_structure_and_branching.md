# Code Structure and Branching Labeling Script

## Overview

Comprehensive pipeline for processing GitHub repository data across multiple team projects. Integrates data cleaning, enrichment, LLM-based labeling, and anonymization into a unified workflow.

## Features

- Review comment cleaning and username extraction
- PR and commit data enrichment
- Bot filtering
- Timestamp normalization to UTC
- Branch name imputation
- LLM-powered code structure analysis
- Multi-dimensional event labeling
- Author anonymization support
- Automated file organization

## Prerequisites

### Required Libraries
```bash
pip install pandas numpy ollama python-dateutil tqdm
```

### Ollama Setup
```bash
# Install Ollama from https://ollama.ai

# Pull required model
ollama pull llama3.2:3b
```

### Directory Structure
```
project/
├── data/
│   └── csv/
│       ├── year-long-project-team-1/
│       │   ├── team-1_all_pull_requests.csv
│       │   ├── team-1_PR_commits.csv
│       │   ├── team-1_commit_file_changes.csv
│       │   └── team-1_review-comments.csv
│       └── year-long-project-team-2/
│           └── [similar structure]
└── confidential/
    └── anonymized_usernames.json
```

## Configuration

### Global Settings
```python
MODEL_NAME = "llama3.2:3b"          # Ollama model for LLM tasks
ANONYMIZE = True                     # Enable/disable anonymization
```

### Anonymization Setup

Create mapping file at `../../confidential/anonymized_usernames.json`:
```json
{
  "RealName1": "Student1",
  "RealName2": "Student2",
  "real.email@domain.com": "Student3"
}
```

## Usage
```bash
python combined_pipeline.py
```

## Pipeline Stages

### Stage 1: Cleaning and Enrichment

#### 1.1 Review Comment Cleaning

**Function:** `clean_review_comments(team_folder)`

Extracts usernames from dictionary-formatted author fields and normalizes timestamps.

**Process:**
- Locates review-comments.csv files
- Extracts usernames from dict format: `{'username': 'name'}` → `name`
- Converts timestamps to UTC Z format
- Overwrites original files with cleaned data

**Expected Input:**
```csv
pr_id,author,created_at,comment_body
1,{'username': 'john'},2024-01-15T10:30:00,Great work
```

**Output:**
```csv
pr_id,author,created_at,comment_body
1,john,2024-01-15T10:30:00Z,Great work
```

#### 1.2 PR and Commit Enrichment

**Function:** `enrich_prs_and_comments(team_folder)`

Adds computed metrics to PR and review comment data.

**Enrichments Added to PRs:**
- `top_file`: File with most changes in the PR
- `top_file_change_%`: Percentage of total PR changes in top file
- `docs_updated`: Boolean indicating if documentation was modified

**Enrichments Added to Comments:**
- `order_of_review`: Classification as "first", "second", or "additional"

**Process:**
1. Filters PRs and comments to only include those with commits
2. Groups commits by PR and calculates file-level statistics
3. Identifies top changed file per PR
4. Ranks review comments chronologically per PR

### Stage 2: Label Generation

#### 2.1 Bot Filtering

Automatically removes bot-generated PRs and commits using pattern matching.

**Filtered Patterns:**
- `[bot]` suffix
- `bot-` prefix or `-bot` suffix
- Specific bots: dependabot, github-actions, renovate, greenkeeper, codecov, snyk-bot, github-classroom

#### 2.2 Timestamp Normalization

**Function:** `normalize_timestamp_to_utc_z(timestamp_str)`

Converts all timestamps to UTC with Z suffix format.

**Examples:**
```
2024-01-15T10:30:00-08:00  →  2024-01-15T18:30:00Z
2024-01-15T10:30:00        →  2024-01-15T10:30:00Z
```

#### 2.3 Event Labeling

Generates seven dimensions of labels for repository events.

##### Features Per Branch

**Labels:** `one Features Per Branch`, `multiple Features Per Branch`

**Logic:** Counts PRs per branch

**Example:**
- Branch "feature/login" with 1 PR → "one Features Per Branch"
- Branch "develop" with 5 PRs → "multiple Features Per Branch"

##### Branch Name Quality

**Labels:** `Meaningful Branch Name`, `Random Branch Name`

**Logic:** LLM evaluates if branch name reflects PR purpose

**Auto-labeled:** main/master → "Random Branch Name"

**LLM Assessed Examples:**
- Meaningful: feature/authentication, fix/navbar-bug, refactor_api
- Random: test, final, update, misc, newbranch

##### Feature Size

**Labels:** `Small Feature Size`, `Large Feature Size`

**Logic:** Net new lines per commit (additions - deletions, when additions > deletions)

**Threshold:** 50 lines
- Less than 50 → Small
- 50 or more → Large

##### Refactor Size

**Labels:** `Small Refactor Size`, `Large Refactor Size`

**Logic:** Total modified lines per file (additions + deletions)

**Threshold:** 50 lines
- Less than 50 → Small
- 50 or more → Large

##### Repository Status

**Labels:** `up-to-date`, `outdated`

**Logic:** Based on `was_up_to_date_at_merge` column
- True → "up-to-date"
- False → "outdated"

##### PR Status

**Labels:** `closed`, `still_open`, `merged`

**Logic:** Based on `state` column
- "open" → "still_open"
- "closed" → "closed"

##### Merge State

**Labels:** `no_merge`, `self_merge`, `reviewed_merge`

**Logic:**
- No `merged_at` → "no_merge"
- `merged_by` equals `pr_author` → "self_merge"
- `merged_by` differs from `pr_author` → "reviewed_merge"

#### 2.4 Timestamp Adjustment

**Function:** `adjust_merge_timestamps(combined_df)`

Ensures merge events occur chronologically after the last commit.

**Priority:**
1. Use `merged_at` timestamp if available
2. Use last commit timestamp + 1 second

### Stage 3: Post-Processing

#### 3.1 Branch Name Cleaning

**Function:** `clean_and_impute_branch_names(input_path, output_path)`

Fills missing branch names using PR ID mapping.

**Process:**
1. Converts PR IDs to consistent integer format
2. Creates mapping of PR ID → branch name
3. Fills missing values using the mapping
4. Saves cleaned data to clean/ subdirectory

#### 3.2 Anonymization

Applied to three data points if enabled:
- PR authors
- Commit authors
- Branch names (username components)

**Process:**
- Case-insensitive pattern matching
- Replaces all occurrences of real names with anonymized versions
- Applied across all output files

## Output Files

### Primary Outputs

#### Event Labels CSV

**Location:** `data/csv/code_structure_branching_labels_{team_name}_anonymized.csv`

**Columns:**
- `pr_id`: Pull request identifier
- `pr_author`: Author username (anonymized if enabled)
- `created_at`: Event timestamp (UTC Z format)
- `branch_name`: Branch name (anonymized if enabled)
- `event`: Specific event label
- `main_label`: Event category
- `llm_output`: Reasoning or calculation details
- `llm_timestamp`: When label was generated

**Example:**
```csv
pr_id,pr_author,created_at,branch_name,event,main_label,llm_output
1,Student1,2024-01-15T10:30:00Z,feature/login,Meaningful Branch Name,Branch Name,LLM: clearly relates to authentication
1,Student1,2024-01-15T10:30:00Z,feature/login,Small Feature Size,Feature Size,rule-based: 35 feature lines
```

#### LLM Reasoning CSV

**Location:** `data/csv/{team_name}/graphs/reasoning/{team_name}_all_llm_reasoning_anonymized.csv`

Contains detailed LLM reasoning for branch name assessments.

**Columns:**
- `pr_id`
- `pr_author`
- `created_at`
- `branch_name`
- `pr_title`
- `pr_description`
- `branch_naming_label`
- `llm_reasoning`
- `llm_timestamp`

#### Cleaned Labels CSV

**Location:** `data/csv/clean/code_structure_branching_labels_{team_name}_anonymized.csv`

Version with imputed branch names.

### Modified Input Files

The pipeline modifies original files in place:

#### Enriched PRs

**Modified:** `{team_name}_all_pull_requests.csv`

**Added Columns:**
- `top_file`
- `top_file_change_%`
- `docs_updated`

#### Enriched Review Comments

**Modified:** `{team_name}_review-comments.csv`

**Added Columns:**
- `order_of_review`

**Cleaned:**
- `author` (username extraction)
- `created_at` (UTC Z format)

## Function Reference

### Data Cleaning Functions

#### clean_review_comments(team_folder)

Cleans review comment files by extracting usernames and normalizing timestamps.

**Parameters:**
- `team_folder` (Path): Team directory containing CSV files

#### enrich_prs_and_comments(team_folder)

Adds computed metrics to PR and review comment data.

**Parameters:**
- `team_folder` (Path): Team directory containing CSV files

#### clean_and_impute_branch_names(input_path, output_path)

Imputes missing branch names based on PR ID mapping.

**Parameters:**
- `input_path` (str): Path to input CSV
- `output_path` (str): Path to output CSV

### Timestamp Functions

#### normalize_timestamp_to_utc_z(timestamp_str)

Converts any timestamp format to UTC with Z suffix.

**Parameters:**
- `timestamp_str` (str): Timestamp in any format

**Returns:**
- str: Normalized timestamp (YYYY-MM-DDTHH:MM:SSZ)

#### adjust_merge_timestamps(combined_df)

Adjusts merge event timestamps for chronological ordering.

**Parameters:**
- `combined_df` (DataFrame): Combined events dataframe

**Returns:**
- DataFrame: Updated dataframe

### Branch Processing Functions

#### get_unique_branch_names(prs_df)

Extracts unique branch names from PR data.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- list: Unique branch names

#### get_branch_pr_mapping(prs_df)

Creates mapping of branch names to PR information.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- dict: Mapping of branch names to list of PR details

### Anonymization Functions

#### load_anonymization_mapping()

Loads anonymization mapping from JSON file.

**Returns:**
- dict: Mapping of real names to anonymized names

#### anonymize_column(series, mapping)

Anonymizes a pandas Series using the mapping.

**Parameters:**
- `series` (Series): Data to anonymize
- `mapping` (dict): Name mapping

**Returns:**
- Series: Anonymized data

#### anonymize_branch_names(series, mapping)

Anonymizes branch names by replacing username components.

**Parameters:**
- `series` (Series): Branch names
- `mapping` (dict): Name mapping

**Returns:**
- Series: Anonymized branch names

### LLM Functions

#### ask_ollama(prompt)

Sends classification prompt to local Ollama instance.

**Parameters:**
- `prompt` (str): Classification prompt

**Returns:**
- str: LLM response

#### assess_branch_meaningfulness(branch_name, pr_title, pr_description)

Evaluates if branch name is meaningful using LLM.

**Parameters:**
- `branch_name` (str): Branch name to assess
- `pr_title` (str): PR title for context
- `pr_description` (str): PR description for context

**Returns:**
- tuple: (label, llm_output)

### Labeling Functions

#### label_features_per_branch(prs_df)

Generates features per branch labels.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- DataFrame: Labeled events

#### label_branch_names(prs_df)

Generates branch name quality labels using LLM.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- tuple: (labels_df, llm_reasoning_df)

#### label_feature_size(commits_df, prs_df, pr_created_at_lookup)

Generates feature size labels per commit.

**Parameters:**
- `commits_df` (DataFrame): Commits dataframe
- `prs_df` (DataFrame): Pull requests dataframe
- `pr_created_at_lookup` (dict): PR ID to timestamp mapping

**Returns:**
- DataFrame: Labeled events

#### label_refactor_size(commits_df, prs_df, pr_created_at_lookup)

Generates refactor size labels per file.

**Parameters:**
- `commits_df` (DataFrame): Commits dataframe
- `prs_df` (DataFrame): Pull requests dataframe
- `pr_created_at_lookup` (dict): PR ID to timestamp mapping

**Returns:**
- DataFrame: Labeled events

#### label_repo_status(prs_df)

Generates repository status labels.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- DataFrame: Labeled events

#### label_pr_status(prs_df)

Generates PR status labels.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- DataFrame: Labeled events

#### label_merge_state(prs_df)

Generates merge state labels.

**Parameters:**
- `prs_df` (DataFrame): Pull requests dataframe

**Returns:**
- DataFrame: Labeled events

### Diagnostic Functions

#### diagnose_timestamp_issues(df)

Checks for timestamp issues in dataframe.

**Parameters:**
- `df` (DataFrame): Dataframe to check

**Output:** Prints diagnostic information

### Main Processing

#### process_all_teams()

Main orchestration function that runs the entire pipeline.

**Process:**
1. Locates team folders
2. Cleans review comments
3. Enriches PR and comment data
4. Filters bots
5. Normalizes timestamps
6. Generates all labels
7. Adjusts merge timestamps
8. Applies anonymization
9. Saves outputs
10. Cleans branch names

## Example Output
```
======================================================================
STEP 1: CLEANING AND ENRICHING FILES
======================================================================

======================================================================
[INFO] Processing: year-long-project-team-1
======================================================================

[INFO] Cleaning: year-long-project-team-1_review-comments.csv
[INFO] Sample before → after:
   {'username': 'john'}  →  john
   {'username': 'jane'}  →  jane
[INFO] Converting 'created_at' to UTC Z format (if needed)...
[SUCCESS] Overwritten cleaned file: year-long-project-team-1_review-comments.csv

======================================================================
[INFO] Enriching data for: year-long-project-team-1
======================================================================
[INFO] Loading input CSVs...
[INFO] Commits loaded: 245, PRs loaded: 52, Comments loaded: 123
[INFO] Filtered PRs: 52 → 52
[INFO] Filtered review comments: 123 → 123
[INFO] Calculating top file metrics per PR...
[INFO] Calculating order_of_review for review comments...
[SUCCESS] Updated PRs saved to: year-long-project-team-1_all_pull_requests.csv
[SUCCESS] Updated review comments saved to: year-long-project-team-1_review-comments.csv

======================================================================
[COMPLETE] All review comments cleaned and files enriched
======================================================================

======================================================================
STEP 2: GENERATING LABELS
======================================================================

============================================================
Processing year-long-project-team-1...
============================================================
Found commits file: year-long-project-team-1_commit_file_changes.csv
   Using file-level commit data (best for granular analysis)
Loading PRs from: year-long-project-team-1_all_pull_requests.csv
[INFO] Filtered out 3 bot PRs
[INFO] Created timestamp lookup for 49 PRs
[INFO] Processing 15 unique branch names across 49 PRs
Anonymizing PR authors...
Anonymizing branch names...
Loading commits from: year-long-project-team-1_commit_file_changes.csv
[INFO] Filtered out 5 bot commits
Anonymizing commit authors...

Generating Code Structure / Branching Labels...
  - Features per branch (one, multiple)...
    Found 2 branches used by multiple PRs
      'develop': 3 PRs
    Generated 49 events
  - Branch names (meaningful, random)...
  Evaluating branch naming via Ollama...
  Branch naming: 100%|████████████████| 15/15 [00:45<00:00,  3.02s/it]
    Generated 49 events
  - Feature size (small, large)...
    Generated 178 events
  - Refactor size (small, large)...
    Generated 542 events
  - Repository status (up-to-date, outdated)...
Generating repository status labels based on 'was_up_to_date_at_merge'...
Generated 45 repository status labels
    Generated 45 events
  - PR status (closed, still_open)...
    Generated 49 events
  - Merge state (no_merge, self-merge, reviewed_merge)...
    Generated 49 events
  Adjusting merge event timestamps for chronological ordering...
    Adjusted 45 merge event timestamps

All 961 events have valid timestamps

Saved combined event labels to: code_structure_branching_labels_year-long-project-team-1_anonymized.csv
Anonymized authors in output:
   Student1: 234 events
   Student2: 198 events
   Student3: 156 events
   Student4: 145 events
   Student5: 228 events
Saved LLM reasoning data to: year-long-project-team-1/graphs/reasoning/year-long-project-team-1_all_llm_reasoning_anonymized.csv

Cleaning branch names...
Loading data from code_structure_branching_labels_year-long-project-team-1_anonymized.csv...
Found 15 records with missing branch_name initially.
--------------------------------------------------
Cleaning complete.
-> Successfully imputed 15 missing branch names based on matching pr_id.
-> The cleaned data is saved to: data/csv/clean/code_structure_branching_labels_year-long-project-team-1_anonymized.csv

============================================================
ALL TEAMS PROCESSED
============================================================
Anonymization was ENABLED for all outputs
============================================================
```

## Error Handling

The pipeline includes comprehensive error handling:
- Skips teams with missing required files
- Continues processing after individual errors
- Reports detailed error messages with context
- Validates data integrity at each stage

## Performance Notes

- LLM calls for branch naming: ~3 seconds per branch
- Total processing time: 5-15 minutes per team (varies with PR count)
- Memory usage: Moderate (processes one team at a time)

## Troubleshooting

### No team folders found

**Issue:** Pipeline finds no teams to process

**Solution:** Verify directory structure matches expected format with `year-long-project-team-*` pattern

### Missing required files

**Issue:** Team skipped due to missing CSV files

**Solution:** Ensure each team folder contains:
- `*_all_pull_requests.csv`
- `*_PR_commits.csv` or `*_commit_file_changes.csv`
- `*_review-comments.csv`

### Ollama connection error

**Issue:** LLM calls fail with connection error

**Solution:**
```bash
# Ensure Ollama is running
ollama serve

# Verify model is available
ollama list
```

### Anonymization not applied

**Issue:** Output contains real names despite ANONYMIZE=True

**Solution:** Verify mapping file exists at `../../confidential/anonymized_usernames.json` and contains valid JSON

### Timestamp parsing errors

**Issue:** Timestamps not normalized correctly

**Solution:** Check input CSV timestamp format. Pipeline supports ISO 8601 formats but may fail on non-standard formats

## Notes

- Original PR and comment CSV files are modified in place
- Event labels and cleaned labels are saved to new files
- Bot filtering is automatic and cannot be disabled
- Anonymization applies to all text fields containing usernames
- LLM assessments are cached per unique branch name
- Pipeline is idempotent (can be run multiple times safely)