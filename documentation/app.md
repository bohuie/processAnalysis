# GitHub Repository Data Extraction Script

## Overview

This script extracts comprehensive data from a single GitHub repository, including pull requests, commits, file changes, and review comments.

## Features

- Extracts all pull requests from a specified repository
- Captures commit data associated with pull requests
- Records file changes for each commit
- Collects review comments and discussions
- Supports orphan commit extraction (commits not associated with any PR)
- Exports data in both JSON and CSV formats
- Configurable README exclusion for log/weekly PRs

## Prerequisites

- Python 3.x
- GitHub API access token (for authentication)
- Required dependencies:
  - `pathlib`
  - `datetime`
  - Custom `PullRequestExtractor` module from `src.extractors`

## Configuration

The script uses the following configuration parameters:

### Required Settings

- **REPO_OWNER**: GitHub organization or username (default: "COSC-499-W2023")
- **REPO_NAME**: Target repository name (default: "year-long-project-team-15")

### Optional Settings

- **OUTPUT_DIR**: Output directory for extracted data (default: "./data")
- **SAVE_JSON**: Export data as JSON files (default: True)
- **SAVE_CSV**: Export data as CSV files (default: True)
- **INCLUDE_ORPHANS**: Include commits not in any PR (default: True)
- **ORPHAN_BRANCH**: Branch to scan for orphan commits (default: "master")
- **EXCLUDE_README**: Exclude README from log/weekly PRs (default: False)

## Usage

### Basic Execution
```bash
python script_name.py
```

### Customizing Configuration

Edit the configuration section in the main block:
```python
REPO_OWNER = "your-org-name"
REPO_NAME = "your-repo-name"
OUTPUT_DIR = "./custom-output"
SAVE_JSON = True
SAVE_CSV = True
INCLUDE_ORPHANS = True
ORPHAN_BRANCH = "main"
EXCLUDE_README = False
```

## Output Structure

The script creates the following directory structure:
```
data/
├── json/
│   └── {repo_name}/
│       └── [JSON files]
└── csv/
    └── {repo_name}/
        ├── {repo_name}_all_pull_requests.csv
        ├── commits.csv
        ├── file_changes.csv
        └── review_comments.csv
```

## Function Reference

### extract_repository_data()

Main extraction function that orchestrates the data extraction process.

**Parameters:**
- `repo_owner` (str): GitHub organization or username
- `repo_name` (str): Repository name
- `output_base_dir` (str): Base directory for output files
- `save_json` (bool): Enable JSON export
- `save_csv` (bool): Enable CSV export
- `include_orphan_commits` (bool): Include commits not in PRs
- `branch_for_orphans` (str): Branch to scan for orphan commits
- `exclude_readme` (bool): Exclude README from log/weekly PRs

**Returns:**
- Dictionary containing extraction results with keys:
  - `repo_name`: Name of the repository
  - `status`: Extraction status (success/failed)
  - `pull_requests_extracted`: Count of extracted PRs
  - `output_files`: List of generated output files
  - `errors`: List of errors encountered

## Output Files

### CSV Files

1. **Pull Requests CSV**: Contains all pull request metadata
2. **Commits CSV**: Contains commit information linked to PRs
3. **File Changes CSV**: Contains file-level changes for each commit
4. **Review Comments CSV**: Contains review comments and discussions

### JSON Files

Raw JSON data for all extracted entities, organized by type.

## Error Handling

The script includes comprehensive error handling:
- Catches and logs extraction errors
- Provides detailed traceback for debugging
- Returns error status in results dictionary
- Exits with status code 1 on failure

## Example Output
```
================================================================================
GITHUB SINGLE REPOSITORY DATA EXTRACTION
================================================================================
================================================================================
EXTRACTING: COSC-499-W2023/year-long-project-team-15
================================================================================
Started: 2025-11-15 10:30:00
Output directory: ./data
Include orphan commits: True
Exclude README from log PRs: False
================================================================================

[INFO] Connecting to GitHub API...
[INFO] Fetching pull requests...

================================================================================
EXTRACTION COMPLETE
================================================================================
Pull Requests: 45

Output files:
  ✓ PRs: ./data/csv/year-long-project-team-15/year-long-project-team-15_all_pull_requests.csv
  ✓ Commits: ./data/csv/year-long-project-team-15/commits.csv
  ✓ File Changes: ./data/csv/year-long-project-team-15/file_changes.csv
  ✓ Comments: ./data/csv/year-long-project-team-15/review_comments.csv
  ✓ JSON: ./data/json/year-long-project-team-15/
================================================================================
Finished: 2025-11-15 10:35:00
================================================================================
```

## Notes

- Requires valid GitHub authentication token
- API rate limits may apply for large repositories
- Execution time varies based on repository size and API response times
- Ensure sufficient disk space for large data exports