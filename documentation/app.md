# GitHub Data Extraction Script — Comprehensive Reference

This document describes [scripts/app.py](../scripts/app.py), the main data extraction and enrichment script for the processAnalysis project. It orchestrates GitHub API calls, enriches PR metadata, and generates the CSVs consumed by downstream labeling and analysis pipelines.

## Overview & Purpose

[scripts/app.py](../scripts/app.py) is a **single-purpose data extraction and enrichment tool**. It:
1. Connects to GitHub API using `PullRequestExtractor`
2. Fetches PRs, commits, file changes, and review comments
3. **Enriches** PRs with computed metrics (reviewers count, lines added/deleted, merge status, etc.)
4. Writes standardized CSV/JSON files for downstream labeling

**Not responsible for:** filtering, anonymization, analysis, or transformations — those are handled by downstream modules ([event_labelling/](../event_labelling/), [process_model/](../process_model/), [analysis.py](../analysis.py)).

## Entry Point & Execution

Run from the **project root**:

```bash
python scripts/app.py
```

The script prints diagnostic output:
```
[DEBUG] Project root: /Users/manu/Documents/GitHub/processAnalysis
[DEBUG] Python path: ['/Users/manu/Documents/GitHub/processAnalysis', ...]
[DEBUG] Successfully imported PullRequestExtractor
[INFO] Connecting to GitHub API...
[INFO] Fetching pull requests...
[INFO] Enriching PR data...
...
[SUCCESS] Saved X pull requests to: data/csv/year-long-project-team-1/
```

## Configuration & Parameters

Edit the `## CONFIGURATION ##` section near the bottom of [scripts/app.py](../scripts/app.py) to customize:

```python
REPO_OWNER = "COSC-499-W2023"          # GitHub organization
REPO_NAMES = [                          # List of repos to extract
    "year-long-project-team-2",
    "year-long-project-team-8",
    # ... more repos
]
OUTPUT_DIR = "./data"                  # Where to save CSVs/JSONs
SAVE_JSON = True                        # Generate JSON output
SAVE_CSV = True                         # Generate CSV output (required!)
INCLUDE_COMMITS = True                  # Extract commit-level data
INCLUDE_FILES = True                    # Extract file-level changes
INCLUDE_COMMENTS = True                 # Extract review comments
```

## Core Dependencies & Imports

### Python Standard Library
- **`os`, `sys`, `json`, `csv`, `traceback`** — File I/O, serialization, debugging
- **`pathlib.Path`** — Cross-platform file path handling
- **`typing`** — Type hints for function signatures
- **`datetime`** — Timestamp generation
- **`concurrent.futures.ThreadPoolExecutor`** — Parallel PR enrichment (5 workers)

### Custom Modules

#### [src/extractors/pull_request_extractor.py](../src/extractors/pull_request_extractor.py) — **Core Data Fetching**
**Location:** [src/extractors/pull_request_extractor.py](../src/extractors/pull_request_extractor.py)  
**Purpose:** Pure API abstraction for GitHub data retrieval.  
**Key class:** `PullRequestExtractor`  
**Main methods:**
- `extract_all_pull_requests(state="all")` — fetches all PRs for a repo (paginated)
- `extract_pull_request_by_id(pr_id)` — fetches single PR details (merge status, conflict info, etc.)
- `extract_commits_from_pr(pr_id)` — lists all commits in a PR
- `extract_commit_details(commit_sha)` — fetches file changes for a single commit
- `extract_pr_file_changes(pr_id)` — all files modified in a PR (additions, deletions, status)
- `extract_pr_reviews(pr_id)` — review objects (when reviewer clicked "Review changes")
- `extract_pr_all_comments(pr_id)` — inline comments, conversation comments, and review bodies
- `compare_commits(base_sha, head_sha)` — checks if head is behind base (for `was_up_to_date_at_merge`)

**Why it matters:** Handles authentication, pagination, rate-limit retries, and API errors. Errors here halt extraction for that repo.

**Example from code:**
```python
extractor = PullRequestExtractor(
    repo_owner='COSC-499-W2023',
    repo_name='year-long-project-team-1',
    need_auth=True
)
all_prs = extractor.extract_all_pull_requests(state="all")  # Returns list of PR objects
```

## Processing Pipeline (Detailed)

### Stage 1: Initialization & Validation
1. Resolve project root (line 12-16)
2. Validate imports (line 19-26) — aborts if `PullRequestExtractor` fails to load
3. Create output directories: `data/csv/repo_name/` and `data/json/repo_name/` (lines 507-513)

**Debug output you'll see:**
```
[DEBUG] Project root: /Users/manu/Documents/GitHub/processAnalysis
[ERROR] Failed to import PullRequestExtractor: ModuleNotFoundError: No module named 'src.extractors'
```
If you see the ERROR, the Python path isn't set correctly. Usually means you're not running from project root.

### Stage 2: GitHub Connection & Raw PR Extraction
```python
extractor = PullRequestExtractor(repo_owner, repo_name, need_auth=True)
pull_requests = extractor.extract_all_pull_requests(state="all")
```

**What happens:**
- Loads `GITHUB_TOKEN` from `.env` or environment (line 520)
- If no token: rate limits are ~60 requests/hour. **With token: ~5000 requests/hour.**
- Fetches PRs in pages of 100 (default `DEFAULT_RESULTS_PER_PAGE`)
- Returns raw PR objects from GitHub API

**Common issues:**
- **"401 Unauthorized"** → Bad/missing `GITHUB_TOKEN`. Create `.env` with valid token.
- **"403 Forbidden"** → Rate limit exceeded. Wait 1 hour or increase token quota.
- **Empty list** → Repo has no PRs (unlikely for team repos).

### Stage 3: Pre-Cache File Changes (Optimization)
```python
file_changes_cache = {}
for pr in pull_requests:
    pr_id = pr["number"]
    file_changes_cache[pr_id] = extractor.extract_pr_file_changes(pr_id)
```

**Why:** Fetches all file changes upfront to avoid redundant API calls during parallel enrichment. File changes are needed for metrics like `lines_added`, `lines_deleted`, `files_changed`, `docs_updated`.

**Performance:** For 200 PRs, this makes ~200 API calls upfront (instead of 200 per enrichment function).

### Stage 4: Parallel PR Enrichment
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(enrich_single_pr, (pr, extractor, file_changes_cache))
        for pr in pull_requests
    ]
```

Each thread calls `enrich_single_pr(pr, extractor, file_changes_cache)` which computes:

| Computed Field | Source | Logic | Use Case |
|---|---|---|---|
| `merged_by` | `extract_pull_request_by_id()` | GitHub username of person who merged (or None) | Track who merges PRs |
| `was_up_to_date_at_merge` | `compare_commits(base_sha, head_sha)` | `behind_by == 0` (head = base at merge time) | Detect stale merges (coordination issues) |
| `has_conflicts` | `mergeable_state == "dirty"` | PR had merge conflicts | Quality metric |
| `num_reviewers` | `extract_pr_reviews(pr_id)` | Unique reviewer count (from review objects) | Review coverage |
| `lines_added`, `lines_deleted`, `files_changed` | File changes cache | Sum of additions/deletions; count of files | PR size metrics |
| `docs_updated` | File changes cache | Any file path contains "readme", "doc", "docs" | Track documentation sync |
| `pr_title`, `pr_description` | `extract_pull_request_by_id()` | Normalized PR text | Context for LLM labeling |

**Example enriched PR:**
```json
{
  "number": 42,
  "merged_at": "2023-09-15T10:30:00Z",
  "merged_by": "alice",
  "was_up_to_date_at_merge": true,
  "has_conflicts": false,
  "num_reviewers": 2,
  "lines_added": 156,
  "lines_deleted": 23,
  "files_changed": 7,
  "docs_updated": true,
  "pr_title": "Feature: User authentication",
  "pr_description": "Implements OAuth2 login flow..."
}
```

**Parallelism benefit:** 5 threads × N PRs → ~5x faster than serial enrichment. For 200 PRs: ~2 min (parallel) vs ~10 min (serial).

### Stage 5: Save Enriched PRs to CSV
```python
save_prs_to_csv(pull_requests, extractor, csv_filepath)
```

**Output file:** `{team_name}_all_pull_requests.csv` (e.g., `year-long-project-team-1_all_pull_requests.csv`)

**Columns (19 total):**
```csv
pr_id,created_at,updated_at,closed_at,merged_at,pr_author,pr_title,pr_description,merged_by,state,head_branch,base_branch,was_up_to_date_at_merge,has_conflicts,docs_updated,num_reviewers,lines_added,lines_deleted,files_changed
42,2023-09-10T08:00:00Z,2023-09-15T10:30:00Z,2023-09-15T10:30:00Z,2023-09-15T10:30:00Z,alice,"Feature: Auth","Implements OAuth...",alice,merged,feature/auth,main,true,false,true,2,156,23,7
```

**Why it matters:** Downstream modules ([code_structure_and_branching.md](code_structure_and_branching.md) labelers, [analysis.py](../analysis.py)) expect these columns. Missing columns = errors or skipped processing.

### Stage 6: Extract Commits (Optional, `INCLUDE_COMMITS=True`)
```python
save_commits_to_csv(extractor, pull_requests, commits_filepath)
```

**Output file:** `{team_name}_commits.csv`  
**Rows:** One per commit per PR (multiple rows per PR if many commits)

**Columns:**
```csv
pr_id,commit_sha,commit_message,commit_date,lines_added,lines_deleted,author,pr_author
42,abc123...,Fix typo in login form,2023-09-10T08:30:00Z,2,1,alice,alice
42,def456...,Add unit tests,2023-09-11T14:00:00Z,45,5,bob,alice
```

**Why it matters:** Commit-level data used by [event_labelling/CodeStructure_Branching/label_feature_size.py](../event_labelling/CodeStructure_Branching/label_feature_size.py) to measure feature size in lines-per-commit. Also used for `[analysis.py](../analysis.py)` to compute project-level stats.

### Stage 7: Extract File Changes (Optional, `INCLUDE_FILES=True`)
```python
save_file_changes_to_csv(extractor, pull_requests, files_filepath)
```

**Output file:** `{team_name}_commit_file_changes.csv`  
**Rows:** One per file per commit (can be many rows per PR)

**Columns:**
```csv
pr_id,pr_author,commit_sha,author,file_path,status,lines_added,lines_deleted,changes,patch_snippet
42,alice,abc123...,alice,src/auth.py,modified,50,10,60,"@@ -10,5 +10,8 @@..."
42,alice,abc123...,alice,tests/test_auth.py,added,150,0,150,"@@ -0,0 +1,150 @@..."
```

**Why it matters:** Used by [event_labelling/CodeStructure_Branching/label_refactor_size.py](../event_labelling/CodeStructure_Branching/label_refactor_size.py) to detect large refactors. Also used for identifying top files per PR (`top_file`, `top_file_change_%`).

### Stage 8: Extract Comments (Optional, `INCLUDE_COMMENTS=True`)
```python
save_comments_to_csv(extractor, pull_requests, comments_filepath)
```

**Output file:** `{team_name}_review-comments.csv`  
**Rows:** Three comment types per PR

**Comment types extracted:**
1. **Inline review comments** — Code review feedback on specific lines (type='inline')
2. **Conversation comments** — General PR discussion (type='conversation')
3. **Review summaries** — When reviewer clicks "Review Changes" → Approve/Request Changes (type='review')

**Columns:**
```csv
pr_id,pr_author,comment_type,comment_id,author,comment_body,created_at,updated_at,state
42,alice,inline,1001,bob,"This variable name is unclear",2023-09-12T10:00:00Z,2023-09-12T10:00:00Z,
42,alice,conversation,1002,charlie,"Great work!",2023-09-13T09:00:00Z,2023-09-13T09:00:00Z,
42,alice,review,1003,bob,"Approved",2023-09-14T15:00:00Z,2023-09-14T15:00:00Z,APPROVED
```

**Why it matters:** Used by [event_labelling/Communication/](../event_labelling/Communication/) module to analyze team communication patterns. Also used by [event_labelling/CodeStructure_Branching/](../event_labelling/CodeStructure_Branching/) to count reviews per PR.

### Stage 9: JSON Output (Optional, `SAVE_JSON=True`)
```python
save_prs_to_json(pull_requests, json_filepath)
```

**Output file:** `{team_name}_pull_requests.json`  
**Format:** Complete JSON dump of enriched PR objects (useful for debugging or custom analysis)

## Output Files Summary

All files written to `data/csv/{team_name}/` and `data/json/{team_name}/`:

| File | Type | Rows | Purpose |
|------|------|------|---------|
| `{team}_all_pull_requests.csv` | CSV | 1 per PR | PR-level metadata & enrichment |
| `{team}_commits.csv` | CSV | 1+ per PR | Commit-level data for sizing metrics |
| `{team}_commit_file_changes.csv` | CSV | 1+ per commit | File-level changes for refactor detection |
| `{team}_review-comments.csv` | CSV | 1+ per PR | All feedback (inline, conversation, reviews) |
| `{team}_pull_requests.json` | JSON | 1 per PR | Raw enriched PR objects (for debugging) |

## Data Dependencies & Debugging

### Missing Output Files?

**Issue:** No CSVs generated  
**Check:**
1. Is `.env` present with valid `GITHUB_TOKEN`?
2. Do repos actually exist in `REPO_NAMES` list?
3. Check error output — look for HTTP status codes (401, 403, 404)

**Example error:**
```
[ERROR] Extraction failed: 404 Client Error: Not Found for url: https://api.github.com/repos/COSC-499-W2023/year-long-project-team-99/pulls
```
→ Repo doesn't exist. Fix spelling in `REPO_NAMES`.

### Inconsistent Row Counts?

**Issue:** `PRs CSV has 50 rows, but commits CSV has 150 rows`  
**Explanation:** This is normal! Commits CSV can have multiple rows per PR (one per commit). Same for file changes and comments.

**To debug:**
```bash
# Count unique PRs in each file
cut -d, -f1 year-long-project-team-1_all_pull_requests.csv | sort -u | wc -l
cut -d, -f1 year-long-project-team-1_commits.csv | sort -u | wc -l
cut -d, -f1 year-long-project-team-1_review-comments.csv | sort -u | wc -l
```
All should have same count of unique `pr_id` values.

### Empty or Zero Values in Metrics?

**Issue:** All `num_reviewers` are 0, `lines_added` all missing, etc.  
**Causes:**
1. PR has no reviews (normal for some PRs)
2. File changes didn't load (API error, missing cached data)
3. Enrichment function crashed silently (check logs for `[WARN]` messages)

**To debug:**
1. Check `lines_added` + `lines_deleted` together:
   ```bash
   # Should be correlated (if high lines_added, expect high lines_deleted or vice versa)
   grep -c ",[0-9]+," year-long-project-team-1_all_pull_requests.csv
   ```
2. Look for `[WARN]` in output:
   ```
   [WARN] Error enriching PR #42: ...
   ```

### API Rate Limiting?

**Issue:** Extraction stops halfway with `403 Forbidden` or `(Retry after XXX seconds)`  
**Why:** Hit GitHub API rate limit (5000/hour with token, 60/hour without)  
**Solution:**
1. Wait 1 hour and re-run
2. Use different token with higher limit
3. Reduce `REPO_NAMES` to test with fewer repos

**Detection:**
```python
# In terminal, check rate limit status:
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/rate_limit
```

## Performance Notes

- **Single repo with ~100 PRs:** ~2-3 minutes (including API calls)
- **20 repos × 100 PRs:** ~45-60 minutes (5 repos in parallel? Not currently implemented, run sequentially)
- **Bottleneck:** GitHub API (not CPU). Each PR = ~10-15 API calls (commits, file changes, reviews, comments)

**To speed up:**
- Reduce `REPO_NAMES` list for testing
- Use repos with fewer PRs
- Ensure `.env` has valid token (5000/hour vs 60/hour is 83x difference)

## Integration with Downstream Modules

After extraction completes:

1. **[event_labelling/CodeStructure_Branching/main.py](../event_labelling/CodeStructure_Branching/main.py)** — Expects `{team}_all_pull_requests.csv`, `{team}_PR_commits.csv`, `{team}_commit_file_changes.csv`, `{team}_review-comments.csv` in `data/csv/{team}/`

2. **[event_labelling/Communication/comm_label.py](../event_labelling/Communication/comm_label.py)** — Expects review-comments CSV for analyzing team communication

3. **[event_labelling/PR/pr_label.py](../event_labelling/PR/pr_label.py)** — Expects PR CSV for PR-level labeling

4. **[analysis.py](../analysis.py)** — Expects PR CSV to compute team-level statistics

5. **[process_model/](../process_model/)** — May use any of the above CSVs for data cleaning or graphing

**Check:** If any downstream script fails, first verify `data/csv/{team}/` contains all expected files and has >0 rows.

## References

- **GitHub API docs:** https://docs.github.com/en/rest/pulls (PR, commits, reviews, comments)
- **PullRequestExtractor source:** [src/extractors/pull_request_extractor.py](../src/extractors/pull_request_extractor.py) (~950 lines, extensive docstrings)
- **Rate limit docs:** https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting
