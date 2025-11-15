# Analysis Script

## Overview

This script analyzes GitHub repository data across multiple team projects, calculating comprehensive statistics at both project and pull request levels. It processes CSV files extracted from GitHub repositories and generates statistical summaries for research or reporting purposes.

## Features

- Processes multiple team repositories simultaneously
- Calculates project-level statistics (mean and standard deviation)
- Calculates PR-level statistics (per pull request averages)
- Identifies most and least productive teams
- Handles various CSV file naming conventions
- Generates multiple output reports
- Provides flexible column name mapping for different data formats

## Prerequisites

### Required Libraries
```python
pandas
numpy
pathlib
glob
os
```

### Required Data Structure

The script expects data to be organized as follows:
```
data/
└── csv/
    ├── year-long-project-team-1/
    │   ├── team-1_all_pull_requests.csv
    │   ├── team-1_PR_commits.csv
    │   ├── team-1_commit_file_changes.csv
    │   └── team-1_review-comments.csv
    ├── year-long-project-team-2/
    │   └── [similar structure]
    └── ...
```

## Configuration

### Directory Setup

The script automatically configures paths based on its location:

- **CURRENT_DIR**: Directory containing the script
- **ROOT**: Project root directory (two levels up from script)
- **DATA_FOLDER**: `{ROOT}/data/csv`
- **OUTPUT_FOLDER**: `{ROOT}/data/analysis`

### Column Name Mappings

The script handles various column naming conventions:
```python
COLUMN_MAPPINGS = {
    'lines_added': ['lines_added', 'line_added', 'additions', 'lines added'],
    'lines_deleted': ['lines_deleted', 'line_deleted', 'deletions', 'lines deleted'],
    'files_changed': ['files_changed', 'changed_files', 'files', 'files altered'],
}
```

## Usage

### Basic Execution
```bash
python script_name.py
```

The script will automatically:
1. Locate all team folders matching `year-long-project-team-*`
2. Process each team's CSV files
3. Calculate statistics
4. Generate output files
5. Display results

## Input Files

### Expected CSV Files Per Team

The script searches for files matching these patterns (in order of preference):

#### 1. Pull Requests File
- `{team_name}_all_pull_requests.csv`
- `{team_name}_PRs.csv`
- `all_pull_requests.csv`
- `pull_requests.csv`

#### 2. Commits File
- `{team_name}_PR_commits.csv`
- `{team_name}_commits.csv`
- `PR_commits.csv`
- `commits.csv`

#### 3. File Changes File
- `{team_name}_commit_file_changes.csv`
- `{team_name}_file_changes.csv`
- `commit_file_changes.csv`
- `file_changes.csv`

#### 4. Reviews File
- `{team_name}_review-comments.csv`
- `{team_name}_reviewcomments.csv`
- `review-comments.csv`
- `reviewcomments.csv`
- `reviews.csv`

## Metrics Calculated

### Team-Level Metrics

For each team, the script calculates:

1. **Number of branches**: Unique branches used
2. **Number of PRs**: Total pull requests
3. **Number of commits**: Total commits across all PRs
4. **Number of files**: Unique files modified
5. **Number of lines of code**: Total lines added and deleted
6. **Number of reviews**: Total code reviews
7. **Number of comments**: Total review comments
8. **Number of merges**: Successfully merged PRs

### Project-Level Statistics

Aggregated statistics across all teams:
- Mean value for each metric
- Standard deviation for each metric

### PR-Level Statistics

Per-pull-request averages:
- Average commits per PR
- Average files changed per PR
- Average lines of code per PR
- Average reviews per PR
- Average comments per PR
- Average merges per PR

## Output Files

The script generates three CSV files in the `data/analysis/` directory:

### 1. table2_statistics.csv

Statistical summary table with:
- Characteristic name
- Project statistics (mean and std dev)
- PR statistics (mean and std dev)

**Example:**
```
Characteristic,Project Statistics,PR Statistics
Number of branches,12.50 (3.20),
Number of PRs,45.30 (10.15),
Number of commits,125.67 (25.40),3.15 (0.85)
```

### 2. team_level_data.csv

Detailed metrics for each team:
- Team name
- All calculated metrics

**Example:**
```
Team,Number of branches,Number of PRs,Number of commits,...
year-long-project-team-1,15,52,145,...
year-long-project-team-2,10,38,98,...
```

### 3. extreme_teams.csv

Identifies teams with extreme values:
- Most productive team (highest lines of code)
- Least productive team (lowest lines of code)

## Helper Functions

### find_file(folder, patterns)

Locates the first matching file from a list of filename patterns.

**Parameters:**
- `folder` (str): Directory to search
- `patterns` (list): List of filename patterns to match

**Returns:**
- str: Path to the first matching file, or None

### normalize_column_name(df, possible_names)

Finds the actual column name from a list of possibilities (case-insensitive).

**Parameters:**
- `df` (DataFrame): Pandas DataFrame
- `possible_names` (list): List of possible column names

**Returns:**
- str: Actual column name in the DataFrame, or None

### safe_sum_column(df, possible_names)

Safely sums a column that might have different names.

**Parameters:**
- `df` (DataFrame): Pandas DataFrame
- `possible_names` (list): List of possible column names

**Returns:**
- float: Sum of the column values, or 0 if column not found

### safe_nunique(df, column)

Safely counts unique values in a column.

**Parameters:**
- `df` (DataFrame): Pandas DataFrame
- `column` (str): Column name

**Returns:**
- int: Number of unique values, or 0 if column not found

## Error Handling

The script includes robust error handling:
- Skips teams with missing required files
- Catches and logs processing errors per team
- Continues processing remaining teams after errors
- Provides clear error messages with team context

## Example Output
```
Found 15 team folders
======================================================================

Processing year-long-project-team-1...
Processing year-long-project-team-2...
...

Saved Table 2 to: data/analysis/table2_statistics.csv
Saved team-level data to: data/analysis/team_level_data.csv
Saved extreme teams to: data/analysis/extreme_teams.csv

======================================================================
TABLE 2: PROJECT CHARACTERISTICS (MEAN, STANDARD DEVIATION)
======================================================================
                Characteristic  Project Statistics   PR Statistics
           Number of branches       12.50 (3.20)                 
                Number of PRs       45.30 (10.15)                 
             Number of commits      125.67 (25.40)     3.15 (0.85)
                Number of files       78.40 (18.22)     1.95 (0.42)
       Number of lines of code    15432.80 (3201.45)  385.82 (89.33)
             Number of reviews       23.60 (8.15)      0.59 (0.18)
            Number of comments       67.90 (22.34)     1.70 (0.54)
              Number of merges       42.10 (9.87)      1.05 (0.12)

======================================================================
OVERALL TOTALS
======================================================================
Total Teams: 15
Total Branches: 188
Total PRs: 680
Total Commits: 1,885
Total Files: 1,176
Total Lines of Code: 231,492
Total Reviews: 354
Total Comments: 1,019
Total Merges: 632

======================================================================
EXTREME TEAMS
======================================================================

Most Productive Team: year-long-project-team-7
  Branches: 18
  PRs: 62
  Commits: 178
  Files: 105
  Lines of Code: 28,543
  Reviews: 35
  Comments: 98
  Merges: 58

Least Productive Team: year-long-project-team-12
  Branches: 8
  PRs: 28
  Commits: 75
  Files: 42
  Lines of Code: 8,234
  Reviews: 12
  Comments: 31
  Merges: 25

======================================================================
ANALYSIS COMPLETE
======================================================================
```

## Statistical Methodology

### Project-Level Statistics

Calculated as the mean and standard deviation of each metric across all teams.

### PR-Level Statistics

1. For each team, calculate the per-PR average (metric / number of PRs)
2. Calculate the mean and standard deviation of these per-PR averages across all teams

This approach provides insight into typical PR characteristics while accounting for different team sizes.

## Troubleshooting

### No team folders found

**Error:** `FileNotFoundError: No team folders found under data/csv/year-long-project-team-*`

**Solution:** Ensure team data folders follow the naming convention `year-long-project-team-*` and are located in `data/csv/`

### Team skipped with warning

**Warning:** `No PRs file found for {team_name}, skipping`

**Solution:** Ensure each team folder contains at least one of the expected pull requests CSV files

### Processing error for specific team

**Error:** `Error processing {team_name}: {error_message}`

**Solution:** Check the CSV file format and ensure required columns are present. The script will continue processing other teams.

## Notes

- The script requires at least the pull requests CSV file for each team
- Other files (commits, file changes, reviews) are optional but recommended for complete analysis
- Line count calculation prioritizes PR-level data, falls back to file changes data if unavailable
- Teams with zero lines of code are excluded from the "least productive" calculation
- Standard deviation uses sample standard deviation (ddof=1) for PR-level statistics

## Customization

To modify the metrics or add new calculations:

1. Add new columns to the `team_stats` dictionary initialization
2. Add calculation logic in the data collection loop
3. Update the `project_stats` and `pr_level_stats` dictionaries
4. Add the new metric to the Table 2 output section