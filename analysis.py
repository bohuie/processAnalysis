import os
import glob
import pandas as pd
import numpy as np
from pathlib import Path


def main():
    """Run team-level analysis and generate summary statistics."""
    # === SETUP ============================================================
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT = CURRENT_DIR
    DATA_FOLDER = os.path.join(ROOT, "data", "csv")
    OUTPUT_FOLDER = os.path.join(ROOT, "data", "analysis")
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # === FIND TEAM FOLDERS ================================================
    team_folders = sorted(
        p for p in glob.glob(os.path.join(DATA_FOLDER, "*"))
        if os.path.isdir(p) and not os.path.basename(p).startswith(".")
    )
    if not team_folders:
        raise FileNotFoundError("No team folders found under data/csv/*")

    print(f"Found {len(team_folders)} team folders")
    print("="*70)
    
    # === HELPER FUNCTIONS =================================================
    def find_file(folder, patterns):
        """Find first matching file from list of patterns."""
        for pattern in patterns:
            potential_path = os.path.join(folder, pattern)
            if os.path.exists(potential_path):
                return potential_path
        return None
    
    def normalize_column_name(df, possible_names):
        """Find the actual column name from a list of possibilities."""
        df_cols = [c.lower() for c in df.columns]
        
        for name in possible_names:
            if name in df.columns:
                return name
            if name.lower() in df_cols:
                idx = df_cols.index(name.lower())
                return df.columns[idx]
        return None
    
    def safe_sum_column(df, possible_names):
        """Safely sum a column that might have different names."""
        col = normalize_column_name(df, possible_names)
        if col:
            return df[col].fillna(0).sum()
        return 0
    
    def safe_nunique(df, column):
        """Safely count unique values in a column."""
        if column in df.columns:
            return df[column].nunique()
        return 0
    
    # === COLUMN NAME MAPPINGS ============================================
    COLUMN_MAPPINGS = {
        'lines_added': ['lines_added', 'line_added', 'additions', 'lines added'],
        'lines_deleted': ['lines_deleted', 'line_deleted', 'deletions', 'lines deleted'],
        'files_changed': ['files_changed', 'changed_files', 'files', 'files altered'],
    }
    
    # === DATA COLLECTION ==================================================
    all_team_data = []
    
    for team_folder in team_folders:
        team_name = os.path.basename(team_folder)
        print(f"\nProcessing {team_name}...")
        
        # Define file patterns
        prs_patterns = [
            f"{team_name}_all_pull_requests.csv",
            f"{team_name}_PRs.csv",
            "all_pull_requests.csv",
            "pull_requests.csv"
        ]
        
        commits_patterns = [
            f"{team_name}_PR_commits.csv",
            f"{team_name}_commits.csv",
            "PR_commits.csv",
            "commits.csv"
        ]
        
        file_changes_patterns = [
            f"{team_name}_commit_file_changes.csv",
            f"{team_name}_file_changes.csv",
            "commit_file_changes.csv",
            "file_changes.csv"
        ]
        
        reviews_patterns = [
            f"{team_name}_review-comments.csv",
            f"{team_name}_reviewcomments.csv",
            "review-comments.csv",
            "reviewcomments.csv",
            "reviews.csv"
        ]
        
        # Find files
        prs_path = find_file(team_folder, prs_patterns)
        commits_path = find_file(team_folder, commits_patterns)
        file_changes_path = find_file(team_folder, file_changes_patterns)
        reviews_path = find_file(team_folder, reviews_patterns)
        
        # Load PRs data
        if not prs_path:
            print(f"  ⚠️ No PRs file found for {team_name}, skipping")
            continue
            
        try:
            prs_df = pd.read_csv(prs_path)
            
            # Initialize team stats
            team_stats = {
                "Team": team_name,
                "Number of branches": safe_nunique(prs_df, "head_branch"),
                "Number of PRs": len(prs_df),
                "Number of commits": 0,
                "Number of files": 0,
                "Number of lines of code": 0,
                "Number of reviews": 0,
                "Number of comments": 0,
                "Number of merges": prs_df["merged_at"].notna().sum() if "merged_at" in prs_df.columns else 0
            }
            
            # Get lines from PRs
            lines_added = safe_sum_column(prs_df, COLUMN_MAPPINGS['lines_added'])
            lines_deleted = safe_sum_column(prs_df, COLUMN_MAPPINGS['lines_deleted'])
            team_stats["Number of lines of code"] = int(lines_added + lines_deleted)
            
            # Load commits
            if commits_path:
                commits_df = pd.read_csv(commits_path)
                team_stats["Number of commits"] = len(commits_df)
            
            # Load file changes
            if file_changes_path:
                file_changes_df = pd.read_csv(file_changes_path)
                team_stats["Number of files"] = safe_nunique(file_changes_df, "file_path")
                
                # If we didn't get line counts from PRs, get from file changes
                if team_stats["Number of lines of code"] == 0:
                    lines_added = safe_sum_column(file_changes_df, COLUMN_MAPPINGS['lines_added'])
                    lines_deleted = safe_sum_column(file_changes_df, COLUMN_MAPPINGS['lines_deleted'])
                    team_stats["Number of lines of code"] = int(lines_added + lines_deleted)
            
            # Load reviews
            if reviews_path:
                reviews_df = pd.read_csv(reviews_path)
                team_stats["Number of reviews"] = len(reviews_df)
                
                # Count comments
                comment_cols = ["comment_body", "body", "review_body", "comment"]
                for col in comment_cols:
                    if col in reviews_df.columns:
                        team_stats["Number of comments"] = reviews_df[col].notna().sum()
                        break
            
            all_team_data.append(team_stats)
            
        except Exception as e:
            print(f"  ❌ Error processing {team_name}: {e}")
    
    # === CREATE DATAFRAME =================================================
    df = pd.DataFrame(all_team_data)
    
    # === CALCULATE PROJECT-LEVEL STATISTICS ===============================
    # These are mean and std dev across all teams (project level)
    project_stats = {
        "Number of branches": (df["Number of branches"].mean(), df["Number of branches"].std()),
        "Number of PRs": (df["Number of PRs"].mean(), df["Number of PRs"].std()),
        "Number of commits": (df["Number of commits"].mean(), df["Number of commits"].std()),
        "Number of files": (df["Number of files"].mean(), df["Number of files"].std()),
        "Number of lines of code": (df["Number of lines of code"].mean(), df["Number of lines of code"].std()),
        "Number of reviews": (df["Number of reviews"].mean(), df["Number of reviews"].std()),
        "Number of comments": (df["Number of comments"].mean(), df["Number of comments"].std()),
        "Number of merges": (df["Number of merges"].mean(), df["Number of merges"].std())
    }
    
    # === CALCULATE PR-LEVEL STATISTICS ====================================
    # For PR-level stats, calculate per-PR averages for each team, then get mean and std dev
    pr_level_stats = {}
    
    # Metrics for PR level
    pr_metrics = ["Number of commits", "Number of files", "Number of lines of code", 
                  "Number of reviews", "Number of comments", "Number of merges"]

    valid_pr_rows = df["Number of PRs"] > 0
    
    for metric in pr_metrics:
        per_pr_values = df.loc[valid_pr_rows, metric] / df.loc[valid_pr_rows, "Number of PRs"]
        
        if not per_pr_values.empty:
            pr_level_stats[metric] = (per_pr_values.mean(), per_pr_values.std(ddof=1))
        else:
            pr_level_stats[metric] = (0, 0)
    
    # Metrics that don't make sense at PR level - set to None
    pr_level_stats["Number of branches"] = (None, None)
    pr_level_stats["Number of PRs"] = (None, None)
    
    # === CREATE TABLE 2 OUTPUT ============================================
    table2_data = []
    for characteristic in ["Number of branches", "Number of PRs", "Number of commits", 
                           "Number of files", "Number of lines of code", "Number of reviews",
                           "Number of comments", "Number of merges"]:
        proj_mean, proj_std = project_stats[characteristic]
        pr_mean, pr_std = pr_level_stats.get(characteristic, (None, None))
        
        # Format project statistics
        proj_stat_str = f"{proj_mean:.2f} ({proj_std:.2f})" if not pd.isna(proj_std) else f"{proj_mean:.2f}"
        
        # Format PR statistics (only for applicable metrics)
        if pr_mean is not None and not pd.isna(pr_std):
            pr_stat_str = f"{pr_mean:.2f} ({pr_std:.2f})"
        else:
            pr_stat_str = ""
        
        table2_data.append({
            "Characteristic": characteristic,
            "Project Statistics": proj_stat_str,
            "PR Statistics": pr_stat_str
        })
    
    table2_df = pd.DataFrame(table2_data)
    
    # === FIND EXTREME TEAMS ===============================================
    # Most productive (highest lines of code)
    most_productive_idx = df["Number of lines of code"].idxmax()
    most_productive_team = df.loc[most_productive_idx]
    
    # Least productive (lowest lines of code, but > 0)
    least_productive_idx = df[df["Number of lines of code"] > 0]["Number of lines of code"].idxmin()
    least_productive_team = df.loc[least_productive_idx]
    
    # === CALCULATE TOTALS =================================================
    totals = {
        "Total Teams": len(df),
        "Total Branches": int(df["Number of branches"].sum()),
        "Total PRs": int(df["Number of PRs"].sum()),
        "Total Commits": int(df["Number of commits"].sum()),
        "Total Files": int(df["Number of files"].sum()),
        "Total Lines of Code": int(df["Number of lines of code"].sum()),
        "Total Reviews": int(df["Number of reviews"].sum()),
        "Total Comments": int(df["Number of comments"].sum()),
        "Total Merges": int(df["Number of merges"].sum())
    }
    
    # === SAVE RESULTS =====================================================
    # Save Table 2
    table2_output = os.path.join(OUTPUT_FOLDER, "table2_statistics.csv")
    table2_df.to_csv(table2_output, index=False)
    print(f"\n✅ Saved Table 2 to: {table2_output}")
    
    # Save detailed team data
    team_data_output = os.path.join(OUTPUT_FOLDER, "team_level_data.csv")
    df.to_csv(team_data_output, index=False)
    print(f"✅ Saved team-level data to: {team_data_output}")
    
    # Save extreme teams info
    extreme_teams_output = os.path.join(OUTPUT_FOLDER, "extreme_teams.csv")
    extreme_df = pd.DataFrame([
        {"Type": "Most Productive", **most_productive_team.to_dict()},
        {"Type": "Least Productive", **least_productive_team.to_dict()}
    ])
    extreme_df.to_csv(extreme_teams_output, index=False)
    print(f"✅ Saved extreme teams to: {extreme_teams_output}")
    
    # === DISPLAY RESULTS ==================================================
    print("\n" + "="*70)
    print("TABLE 2: PROJECT CHARACTERISTICS (MEAN, STANDARD DEVIATION)")
    print("="*70)
    print(table2_df.to_string(index=False))
    
    print("\n" + "="*70)
    print("OVERALL TOTALS")
    print("="*70)
    for key, value in totals.items():
        print(f"{key}: {value:,}")
    
    print("\n" + "="*70)
    print("EXTREME TEAMS")
    print("="*70)
    print(f"\nMost Productive Team: {most_productive_team['Team']}")
    print(f"  Branches: {most_productive_team['Number of branches']}")
    print(f"  PRs: {most_productive_team['Number of PRs']}")
    print(f"  Commits: {most_productive_team['Number of commits']}")
    print(f"  Files: {most_productive_team['Number of files']}")
    print(f"  Lines of Code: {most_productive_team['Number of lines of code']:,}")
    print(f"  Reviews: {most_productive_team['Number of reviews']}")
    print(f"  Comments: {most_productive_team['Number of comments']}")
    print(f"  Merges: {most_productive_team['Number of merges']}")
    
    print(f"\nLeast Productive Team: {least_productive_team['Team']}")
    print(f"  Branches: {least_productive_team['Number of branches']}")
    print(f"  PRs: {least_productive_team['Number of PRs']}")
    print(f"  Commits: {least_productive_team['Number of commits']}")
    print(f"  Files: {least_productive_team['Number of files']}")
    print(f"  Lines of Code: {least_productive_team['Number of lines of code']:,}")
    print(f"  Reviews: {least_productive_team['Number of reviews']}")
    print(f"  Comments: {least_productive_team['Number of comments']}")
    print(f"  Merges: {least_productive_team['Number of merges']}")
    
    print("\n" + "="*70)
    print("✅ ANALYSIS COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
