# Data Processing Pipeline Documentation

This document details the complete two-stage data processing pipeline:
**Data Extraction and Transformation** (handled by
`pull_request_extractor.py`) and **Data Cleaning and Enrichment**
(handled by `csvFix.py`).

------------------------------------------------------------------------

## 1. Data Extraction and Initial Processing (`pull_request_extractor.py`)

The `PullRequestExtractor` is responsible for fetching raw data from the
GitHub API, applying extensive filtering and initial transformations,
and calculating core metrics before saving the initial CSVs.

### High-Level Summary

-   **Data Source:** GitHub REST API (PRs, Commits, Files, Comments)
-   **Request Policy:** Authenticated requests (`GITHUB_TOKEN`) with
    backoff + rate limit handling
-   **Output:** Saves to `data/csv` and `data/json` (Pull Request CSV
    and Commit CSV)

------------------------------------------------------------------------

## Detailed Data Processing Logic

This section catalogs all detailed data processing and transformation
logic found within the `PullRequestExtractor` that should be separated
into dedicated processing modules.

------------------------------------------------------------------------

## 1. Log Filtering & Pattern Matching

### Purpose

Filters out log-related content from PRs, commits, files, and comments
using regex-based pattern matching.

### Components

#### `LogFilterMixin` Class

-   **Pattern Matching**:

    ``` python
    LOG_PATTERN = re.compile(r'(?<![a-zA-Z])(logs?)(?![a-zA-Z])', re.IGNORECASE)
    ```

    Matches "log" or "logs" as standalone words.

-   **Path Keywords**:\
    `/logs/`, `/log/`, `_logs/`, `_log/`, `logs/`, `log/`

#### Methods

``` python
is_log_pr(pr_title, pr_body) -> bool
is_log_file(filename) -> bool
is_log_commit(commit_message) -> bool
is_log_comment(comment_body) -> bool
```

**Usage Statistics Tracking**

``` python
self.stats = {
    'prs_filtered': 0,
    'commits_filtered': 0,
    'files_filtered': 0,
    'comments_filtered': 0,
}
```

------------------------------------------------------------------------

## 2. File Filtering & Exclusion

### Purpose

Determines which files should be excluded from analysis based on content
type and context.

### Logic

#### README File Detection

``` python
@staticmethod
def is_readme_file(filename: Optional[str]) -> bool:
    return os.path.basename(filename).lower().startswith("readme")
```

#### Conditional File Exclusion

``` python
def should_exclude_file(self, filename, pr_title=None) -> bool:
    # Excludes based on:
    # 1. Log file patterns (if exclude_logs=True)
    # 2. README files in log PRs (if exclude_readme=True)
```

#### File List Filtering

``` python
def filter_files(self, files: List[PullRequestFile], pr_title=None) -> List[PullRequestFile]:
    # Applies exclusion rules to file lists
```

------------------------------------------------------------------------

## 3. Metrics Calculation

### Purpose

Calculates aggregate statistics and metrics for pull requests.

### Calculated Metrics

``` python
def calculate_metrics(self, all_changed_files, pr_title=None) -> Dict:
    return {
        "lines_added": int,
        "lines_deleted": int,
        "files_changed": int,
        "top_file": str,
        "top_file_pct": float,
    }
```

------------------------------------------------------------------------

## 4. Data Transformation & Enrichment

### Purpose

Transforms and enriches raw API data into structured formats with
additional context.

------------------------------------------------------------------------

## 5. Orphan Commit Identification

### Purpose

Identifies commits that exist on a branch but are not associated with
any PR.

------------------------------------------------------------------------

## 6. Merge Status Analysis

### Purpose

Determines if a PR was up-to-date with the base branch at merge time.

------------------------------------------------------------------------

## 7. Data Aggregation & Statistics

Tracks statistics, CSV mappings, deduplication, and pagination.

------------------------------------------------------------------------

# 2. Data Cleaning and Enrichment (`csvFix.py`)

The `OptimizedCSVFixer` performs bulk correction and enrichment of
extracted CSV data using optimized batching, threading, and caching.

------------------------------------------------------------------------

## 2.1 Optimization Architecture

Batching, multithreading, and caching for API performance.

------------------------------------------------------------------------

## 2.2 Commit CSV Fixing (`fix_commits_csv_optimized`)

Fills or corrects: - commit_date\
- file_path\
- lines_added\
- lines_deleted

------------------------------------------------------------------------

## 2.3 PR CSV Fixing (`fix_pr_csv_optimized`)

Adds or enriches: - reviewers\
- num_reviewers\
- is_up_to_date\
- has_conflicts

------------------------------------------------------------------------