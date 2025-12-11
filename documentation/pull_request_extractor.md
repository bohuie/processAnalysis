# Pull Request Extractor

This document describes the extractor tooling that populates the CSV/JSON artifacts consumed by the enrichment and labeling pipeline.

## Overview

The extractor retrieves pull requests, commits, file changes, and review comments. It provides options for pagination, rate-limit handling, and optional authenticated requests.

## Quick setup

Install dependencies and add a GitHub token if needed:

```bash
python -m pip install -r requirements.txt
# Optional: create .env with GITHUB_TOKEN to increase API limits
```

## Usage (high-level)

Use the extractor class in `src.extractors` (the project includes a `PullRequestExtractor` implementation) and write outputs into `data/csv/{repo_folder}/` so downstream scripts can pick them up. Ensure filenames follow the pipeline naming conventions (see below).

## Filenames and important columns

The pipeline expects CSVs with the following filenames and representative columns inside each team folder under `data/csv/`:

- `{team_name}_all_pull_requests.csv`
  - important columns: `pr_id`, `pr_title`, `pr_author`, `head_branch`, `base_branch`, `state`, `created_at`, `merged_at`, `merged_by`, `was_up_to_date_at_merge`, `has_conflicts`, `files_changed`, `line_added`, `line_deleted`

- `{team_name}_PR_commits.csv` (or commits CSV)
  - important columns: `pr_id`, `commit_sha`, `author` (commit author), `commit_date`

- `{team_name}_commit_file_changes.csv` (file-level changes)
  - important columns: `pr_id`, `commit_sha`, `file_path`, `lines_added`, `lines_deleted`, `file_status`

- `{team_name}_review-comments.csv`
  - important columns: `pr_id`, `comment_id`, `author`, `created_at`, `comment_body`

## Notes

- The extractor includes log-PR filtering helpers used by some workflows but downstream scripts expect cleaned/enriched CSVs.
- Ensure extracted CSVs use UTF-8 and consistent ISO 8601 timestamps where possible.

## Rate Limiting

### Automatic Handling

The extractor includes sophisticated rate limit management:

1. **Pre-request Check:** Checks remaining requests before each call
2. **Automatic Waiting:** Waits until rate limit reset when needed
3. **Exponential Backoff:** Increases wait time on repeated failures
4. **Buffer Time:** Adds 5-second buffer before rate limit reset

### Rate Limit Status

```python
remaining, reset_time = extractor.check_rate_limit()
print(f"Remaining: {remaining}, Resets at: {reset_time}")
```

### Manual Rate Limit Handling

```python
# Wait for rate limit reset
extractor.wait_for_rate_limit_reset(reset_time)
```

## Error Handling

### Request Retry Logic

All API requests use exponential backoff:

```python
response = extractor.make_request_with_backoff(
    url="https://api.github.com/...",
    max_retries=5,
    wait_time=60,
    backoff_factor=2.0
)
```

**Retry Behavior:**

- Attempt 1: Wait 60 seconds
- Attempt 2: Wait 120 seconds
- Attempt 3: Wait 240 seconds
- Attempt 4: Wait 480 seconds
- Attempt 5: Wait 960 seconds

### Common Errors

#### 403 Forbidden

**Cause:** Rate limit exceeded or insufficient permissions

**Solution:**

- Add GitHub token to `.env`
- Wait for rate limit reset
- Reduce concurrent requests

#### Empty Response

**Cause:** Network error or invalid URL

**Solution:** Script automatically retries with backoff

#### Missing Fields

**Cause:** GitHub API response structure variation

**Solution:** Script uses defensive field access with defaults

## Statistics and Diagnostics

### Filtering Statistics

```python
extractor.print_filtering_stats()
```

**Output:**

```
============================================================
LOG FILTERING STATISTICS
============================================================
PRs filtered:      5
Commits filtered:  12
Files filtered:    23
Comments filtered: 8
============================================================
```

### Debug Mode

Enable debug output by checking console logs with `[DEBUG]` prefix:

```
[DEBUG] Extracting commits from PR #123
[DEBUG] Found 15 commits in PR #123
[DEBUG] Filtered log-related commit: Update weekly logs
```

## Advanced Usage

### Custom Filtering

```python
# Disable all filtering
extractor = PullRequestExtractor(
    repo_owner="owner",
    repo_name="repo",
    exclude_logs=False,
    exclude_readme=False
)

# Custom blacklist
blacklisted_users = ["bot-user", "automated-pr"]
pr = extractor.extract_pull_request_by_id(
    pr_id=123,
    blacklisted_users=blacklisted_users
)
```

### Date Range Extraction

```python
# Extract commits from specific date range
commits = extractor.extract_commits_from_branch(
    branch_name="main",
    since="2024-01-01T00:00:00Z",
    until="2024-03-31T23:59:59Z"
)
```

### Orphan Commit Analysis

```python
# Get all orphan commits
orphans = extractor.extract_orphan_commits_only(
    branch_name="main",
    max_commits=1000
)

# Save orphan commits separately
extractor.save_branch_commits_to_csv(
    branch_name="main",
    orphans_only=True,
    csv_filename="orphan_commits"
)
```

### Multi-Branch Analysis

```python
# Get all branches
branches = extractor.extract_all_branches()

# Extract commits from each branch
for branch in branches:
    branch_name = branch['name']
    commits = extractor.extract_commits_from_branch(
        branch_name=branch_name,
        max_commits=100
    )
    print(f"{branch_name}: {len(commits)} commits")
```

## Helper Functions

### calculate_metrics()

Calculates PR metrics with filtering.

**Parameters:**
- `all_changed_files` (List[PullRequestFile]): File change list
- `pr_title` (str): PR title (optional)

**Returns:**
- Dict: Metrics including lines added/deleted, files changed, top file

### get_merge_sync_status_from_api()

Determines if PR was up-to-date at merge.

**Parameters:**
- `base_sha` (str): Base commit SHA
- `merge_commit_sha` (str): Merge commit SHA
- `pr_id` (int): PR number (optional)

**Returns:**
- Dict: `was_up_to_date_at_merge`, `was_behind_at_merge`

### find_orphan_commits()

Finds commits not associated with any PR.

**Parameters:**
- `branch` (str): Branch name (default: "main")

**Returns:**
- List[Dict]: Orphan commit dictionaries

## Output Directory Structure

```
data/
├── csv/
│   └── {repo_name}/
│       ├── {repo_name}_all_pull_requests.csv
│       ├── {repo_name}_PR_commits.csv
│       ├── {repo_name}_commit_file_changes.csv
│       ├── {repo_name}_review-comments.csv
│       └── {repo_name}_branch_{branch_name}_commits.csv
└── json/
    └── {repo_name}/
        ├── {owner}_{repo}_PR_{pr_id}.json
        └── {owner}_{repo}_commits_{pr_id}.json
```

## Performance Optimization

### Batch Processing

- Processes up to 100 items per API request
- Uses pagination for large datasets
- Implements safety limits (MAX_PAGES = 50)

### Parallel Operations

Supports concurrent operations through ThreadPoolExecutor:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(extractor.extract_pull_request_by_id, pr_id) 
               for pr_id in pr_ids]
```

### Memory Management

- Processes data in chunks
- Writes to CSV incrementally
- Clears caches periodically

## Troubleshooting

### No data extracted

**Issue:** Empty result sets

**Solutions:**
1. Verify repository exists and is accessible
2. Check authentication token
3. Verify branch names are correct
4. Disable filters temporarily

### Slow extraction

**Issue:** Long processing times

**Solutions:**
1. Reduce `max_commits` parameter
2. Use date range filters
3. Enable CSV-only output (disable JSON)
4. Process fewer branches

### Missing review comments

**Issue:** Empty reviewers list

**Solutions:**
1. Script includes automatic fallback
2. Manually fetch using direct API
3. Check PR has actual comments/reviews

### Import errors

**Issue:** Module import failures

**Solutions:**
1. Script includes fallback classes
2. Verify all dependencies installed
3. Check file paths are correct

## Example Workflows

### Complete Repository Analysis

```python
# Initialize
extractor = PullRequestExtractor(
    repo_owner="your-org",
    repo_name="your-repo",
    need_auth=True,
    exclude_logs=True
)

# Extract all data
prs = extractor.extract_pull_requests_with_pagination(
    pull_request_status="all",
    save_data_to_csv=True,
    include_orphan_commits=True,
    branch_for_orphans="main"
)

# Get statistics
extractor.print_filtering_stats()
```

### Orphan Commit Report

```python
# Find orphans
orphans = extractor.extract_orphan_commits_only(
    branch_name="main"
)

# Save to CSV
extractor.save_branch_commits_to_csv(
    branch_name="main",
    orphans_only=True
)

print(f"Found {len(orphans)} orphan commits")
```

### Multi-Branch Comparison

```python
# Get all branches
branches = extractor.extract_all_branches()

# Analyze each branch
branch_stats = {}
for branch in branches:
    name = branch['name']
    commits = extractor.extract_commits_from_branch(
        branch_name=name,
        identify_orphans=True
    )
    orphan_count = sum(1 for c in commits if c.get('is_orphan'))
    branch_stats[name] = {
        'total': len(commits),
        'orphans': orphan_count
    }

# Print report
for branch, stats in branch_stats.items():
    print(f"{branch}: {stats['total']} commits, {stats['orphans']} orphans")
```

## Key Notes

- All timestamps are in ISO 8601 format
- Authentication highly recommended for production use
- Log filtering uses word boundaries for accuracy
- Orphan detection requires scanning entire branch history
- CSV files use UTF-8 encoding
- Safety limits prevent infinite loops
- Fallback mechanisms ensure data extraction continues on errors
