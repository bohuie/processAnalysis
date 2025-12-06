# Pull Request Extractor

## Overview

Comprehensive GitHub data extraction tool that retrieves pull requests, commits, file changes, and review comments from GitHub repositories. Features intelligent log filtering, bot detection, orphan commit identification, and branch-level analysis.

## Features

- Pull request extraction with pagination
- Commit and file change tracking
- Review comment extraction with fallback mechanisms
- Orphan commit detection (commits not in any PR)
- Branch-level commit analysis
- Smart log filtering (standalone word matching)
- Bot filtering
- README exclusion for log PRs
- Rate limit handling with exponential backoff
- Multi-threaded operations support
- CSV and JSON export

## Prerequisites

### Required Libraries
```bash
pip install requests python-dateutil python-dotenv tqdm
```

### Authentication

Create `.env` file in project root:
```
GITHUB_TOKEN=your_github_personal_access_token
```

**Note:** Authentication is optional but highly recommended to avoid rate limits.

## Quick Start

### Basic PR Extraction
```python
from pull_request_extractor import PullRequestExtractor

# Initialize extractor
extractor = PullRequestExtractor(
    repo_owner="microsoft",
    repo_name="vscode",
    need_auth=True,
    exclude_logs=True
)

# Extract all PRs
prs = extractor.extract_pull_requests_with_pagination(
    pull_request_status="all",
    save_data_to_csv=True,
    include_orphan_commits=True,
    branch_for_orphans="main"
)
```

### Branch Commit Extraction
```python
# Extract commits from a branch
commits = extractor.extract_commits_from_branch(
    branch_name="main",
    max_commits=100,
    identify_orphans=True
)

# Save branch commits to CSV
extractor.save_branch_commits_to_csv(
    branch_name="main",
    orphans_only=True
)
```

## Configuration

### Class Initialization
```python
PullRequestExtractor(
    repo_owner: str,              # Repository owner/organization
    repo_name: str,               # Repository name
    need_auth: bool = True,       # Use GitHub authentication
    request_counter = None,       # Optional request counter
    exclude_readme: bool = False, # Exclude READMEs from log PRs
    exclude_logs: bool = True     # Filter log-related content
)
```

### Class Constants
```python
DEFAULT_RESULTS_PER_PAGE = 100         # Results per API page
RATE_LIMIT_BUFFER_SECONDS = 5          # Buffer before rate limit reset
REQUEST_TIMEOUT_SECONDS = 30           # API request timeout
RETRY_WAIT_TIME = 60                   # Initial retry wait time
MAX_RETRIES = 5                        # Maximum retry attempts
MAX_PAGES = 50                         # Safety limit for pagination
```

## Log Filtering System

### Pattern Matching

The extractor uses intelligent log filtering that matches "log" or "logs" only as standalone words:

**Matches:**
- "Update log file"
- "Add logs directory"
- "/logs/error.log"
- "weekly_logs"

**Does Not Match:**
- "catalog" (contains "log" but not standalone)
- "dialog" (contains "log" but not standalone)
- "analogous" (contains "log" but not standalone)

### Filter Categories

#### 1. Log PRs

Filtered based on PR title and description:
```python
is_log_pr(pr_title="Weekly log update", pr_body="Adding logs for week 5")
# Returns: True
```

#### 2. Log Files

Filtered based on file path and name:
```python
is_log_file("/src/logs/error.log")  # True
is_log_file("changelog.md")         # False (not standalone)
```

#### 3. Log Commits

Filtered based on commit message:
```python
is_log_commit("Update weekly logs")  # True
is_log_commit("Update catalog")      # False
```

#### 4. Log Comments

Filtered based on comment body:
```python
is_log_comment("Check the log files")  # True
is_log_comment("Check the dialog")     # False
```

## Core Functions

### PR Extraction

#### extract_pull_requests_with_pagination()

Extracts all pull requests with pagination support.

**Parameters:**
- `pull_request_status` (str): "all", "open", "closed" (default: "all")
- `result_per_page` (int): Results per page (default: 100)
- `save_data_to_json` (bool): Save to JSON files (default: False)
- `save_data_to_csv` (bool): Save to CSV files (default: True)
- `csv_filename` (str): Custom CSV filename (optional)
- `include_orphan_commits` (bool): Include commits not in PRs (default: True)
- `branch_for_orphans` (str): Branch to scan for orphans (default: "master")

**Returns:**
- List[PullRequest]: List of pull request objects

**Example:**
```python
prs = extractor.extract_pull_requests_with_pagination(
    pull_request_status="closed",
    save_data_to_csv=True,
    csv_filename="repo_prs",
    include_orphan_commits=True,
    branch_for_orphans="main"
)
```

#### extract_pull_request_by_id()

Extracts a single pull request by ID.

**Parameters:**
- `pr_id` (int): Pull request number
- `blacklisted_users` (List[str]): Users to exclude (optional)
- `save_data_to_json` (bool): Save to JSON (default: True)

**Returns:**
- PullRequest or None: Pull request object if found

**Example:**
```python
pr = extractor.extract_pull_request_by_id(
    pr_id=123,
    blacklisted_users=["bot-user"],
    save_data_to_json=True
)
```

### Commit Extraction

#### extract_commits_from_pull_request()

Extracts commits from a specific pull request.

**Parameters:**
- `pr_id` (int): Pull request number
- `blacklisted_users` (List[str]): Users to exclude (optional)
- `save_data_to_json` (bool): Save to JSON (default: False)
- `json_config`: JSON configuration object

**Returns:**
- List[Commit]: List of commit objects

#### extract_commits_from_branch()

Extracts commits from a branch without requiring PR association.

**Parameters:**
- `branch_name` (str): Branch name (default: "main")
- `since` (str): ISO 8601 date - commits after this date (optional)
- `until` (str): ISO 8601 date - commits before this date (optional)
- `max_commits` (int): Maximum commits to fetch (optional)
- `identify_orphans` (bool): Mark orphan commits (default: False)

**Returns:**
- List[Dict]: List of commit dictionaries

**Example:**
```python
commits = extractor.extract_commits_from_branch(
    branch_name="develop",
    since="2024-01-01T00:00:00Z",
    until="2024-12-31T23:59:59Z",
    max_commits=500,
    identify_orphans=True
)
```

#### extract_orphan_commits_only()

Extracts only orphan commits (not associated with any PR).

**Parameters:**
- `branch_name` (str): Branch name (default: "main")
- `since` (str): ISO 8601 date (optional)
- `until` (str): ISO 8601 date (optional)
- `max_commits` (int): Maximum commits (optional)

**Returns:**
- List[Dict]: List of orphan commit dictionaries

**Example:**
```python
orphans = extractor.extract_orphan_commits_only(
    branch_name="main",
    since="2024-01-01T00:00:00Z"
)
```

### File and Comment Extraction

#### extract_pull_request_file_changes()

Extracts file changes from a pull request.

**Parameters:**
- `pr_id` (int): Pull request number
- `results_per_page` (int): Results per page (optional)

**Returns:**
- List[Dict]: List of file change dictionaries

### Branch Operations

#### extract_all_branches()

Extracts all branches from the repository.

**Returns:**
- List[Dict]: List of branch dictionaries

**Example:**
```python
branches = extractor.extract_all_branches()
for branch in branches:
    print(f"Branch: {branch['name']}")
```

### Review Comments

#### _extract_review_comments()

Extracts review comments with automatic fallback.

**Parameters:**
- `pr_id` (int): Pull request number
- `pr_data` (Dict): PR data dictionary
- `blacklisted_users` (List[str]): Users to exclude

**Returns:**
- Tuple[List[User], List[Dict]]: (review_authors, comments)

**Features:**
- Attempts CommentExtractor first
- Falls back to direct API calls
- Extracts both review comments and issue comments
- Deduplicates authors

## CSV Output Files

### 1. Pull Requests CSV

**Filename:** `{repo_name}_all_pull_requests.csv`

**Columns:**
- `pr_id`: Pull request number
- `pr_title`: PR title
- `pr_author`: PR author username
- `head_branch`: Source branch
- `base_branch`: Target branch
- `state`: PR state (open/closed)
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `closed_at`: Close timestamp
- `merged_at`: Merge timestamp
- `merged_by`: User who merged
- `num_commits`: Number of commits
- `num_reviewers`: Number of reviewers
- `reviewers`: Comma-separated reviewer list
- `pr_description`: PR description text
- `mergeable_state`: GitHub mergeable state
- `is_up_to_date`: Up-to-date status
- `was_up_to_date_at_merge`: Up-to-date at merge time
- `has_conflicts`: Conflict status
- `is_self_merged`: Self-merge indicator
- `line_added`: Lines added
- `line_deleted`: Lines deleted
- `total_changes`: Total line changes
- `files_changed`: Number of files changed
- `was_behind_at_merge`: Commits behind at merge
- `top_file`: File with most changes
- `top_file_change_%`: Percentage of changes in top file
- `docs_updated`: Documentation update indicator
- `has_readme_changes`: README change indicator
- `feature_documentation_status`: Documentation status

### 2. Commits CSV

**Filename:** `{repo_name}_PR_commits.csv`

**Columns:**
- `repo_name`: Repository name
- `pr_id`: Associated PR ID (null for orphans)
- `pr_author`: PR author
- `head_branch`: Source branch
- `base_branch`: Target branch
- `commit_sha`: Commit hash
- `author`: Commit author
- `commit_date`: Commit timestamp
- `file_path`: Modified file path
- `lines_added`: Lines added
- `lines_deleted`: Lines deleted
- `commit_message`: Commit message (first line)
- `message_word_count`: Word count in message

### 3. File Changes CSV

**Filename:** `{repo_name}_commit_file_changes.csv`

**Columns:**
- `repo_name`: Repository name
- `pr_id`: Associated PR ID
- `pr_author`: PR author
- `head_branch`: Source branch
- `base_branch`: Target branch
- `commit_sha`: Commit hash
- `commit_author`: Commit author
- `commit_date`: Commit timestamp
- `commit_message`: Commit message (truncated)
- `file_path`: File path
- `file_status`: File status (modified/added/removed/renamed)
- `lines_added`: Lines added to file
- `lines_deleted`: Lines deleted from file
- `total_changes`: Total changes to file
- `previous_filename`: Previous filename (for renames)

### 4. Review Comments CSV

**Filename:** `{repo_name}_review-comments.csv`

**Columns:**
- `pr_id`: Pull request number
- `comment_id`: Comment identifier
- `pr_author`: PR author
- `author`: Comment author
- `comment_body`: Comment text
- `comment_word_count`: Word count
- `created_at`: Creation timestamp
- `updated_at`: Update timestamp
- `user_login`: User login name
- `state`: Comment state
- `order_of_review`: Review order indicator

### 5. Branch Commits CSV

**Filename:** `{repo_name}_branch_{branch_name}_commits.csv`

**Columns:**
- `repo_name`: Repository name
- `branch_name`: Branch name
- `commit_sha`: Commit hash
- `author`: Commit author
- `author_email`: Author email
- `commit_date`: Commit timestamp
- `commit_message`: Commit message (truncated)
- `message_word_count`: Message word count
- `files_changed`: Number of files changed
- `additions`: Total additions
- `deletions`: Total deletions
- `total_changes`: Total changes
- `is_orphan`: Orphan commit indicator
- `pr_id`: Associated PR (null if orphan)

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

## Notes

- All timestamps are in ISO 8601 format
- Authentication highly recommended for production use
- Log filtering uses word boundaries for accuracy
- Orphan detection requires scanning entire branch history
- CSV files use UTF-8 encoding
- Safety limits prevent infinite loops
- Fallback mechanisms ensure data extraction continues on errors