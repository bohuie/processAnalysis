import os
import sys
import pandas as pd
import re
import json
import ast
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import utilities from src/utils
from src.utils.ollama_offline import connect_ollama_offline
from src.utils.connect_groq import connect_groq
from src.utils.label_merge import label_merge_state
from src.utils.anonymize_columns import (
    anonymize_column,
    anonymize_branch_names,
)
from src.utils.enrich_columns import (
    add_top_file_metrics,
    add_docs_updated_flag,
    add_order_of_review,
)
from src.utils.botFilter import (
    remove_bot_prs,
    remove_bot_commits,
    filter_bots_from_multiple_columns,
)

# Import labeling functions
from .label_branch_names import label_branch_names
from .label_features_per_branch import label_features_per_branch
from .label_feature_size import label_feature_size
from .label_refactor_size import label_refactor_size
from .label_repo_status import label_repo_status
from .label_pr_status import label_pr_status
from process_model.clean import create_clean_branching_label_csv

# === SETUP ============================================================
MODEL_NAME = "llama3.2:3b"
RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"
ANONYMIZE = True

# Check AI_MODE toggle
AI_MODE = os.getenv("AI_MODE", "offline").lower()
if AI_MODE == "online":
    ask_llm = connect_groq
    print(f"[INFO] AI_MODE=online, using Groq API")
else:
    ask_llm = connect_ollama_offline
    print(f"[INFO] AI_MODE=offline, using local Ollama")


# === FILE ENRICHMENT =====================================
def enrich_prs_and_comments(team_folder):
    """Enrich PRs with top file metrics and add order_of_review to comments using utility functions."""
    # Call the utility functions that handle all the enrichment
    add_top_file_metrics(team_folder)
    add_docs_updated_flag(team_folder)
    add_order_of_review(team_folder)

def diagnose_timestamp_issues(df):
    """Check for timestamp issues in the final dataframe."""
    if "created_at" not in df.columns:
        print("[WARN] 'created_at' column not present in dataframe — skipping timestamp diagnostics")
        return

    missing = df["created_at"].isna().sum()
    total = len(df)

    if missing > 0:
        print(f"\nWARNING: {missing}/{total} events have missing timestamps")

        missing_df = df[df["created_at"].isna()][["pr_id", "pr_author", "main_label", "event"]].head(10)
        if not missing_df.empty:
            print("  Examples of events with missing timestamps:")
            print(missing_df.to_string(index=False))
    else:
        print(f"\nAll {total} events have valid timestamps")

# === MAIN PROCESSING ==================================================
def process_all_teams():
    """Main function to process all teams."""
    base_path = Path("data/csv/")
    
    if not base_path.exists():
        print(f"Base path '{base_path}' not found!")
        print(f"[INFO] Current working directory: {os.getcwd()}")
        print(f"[INFO] Please ensure data folder exists in the current directory")
        return
    
    team_folders = sorted(base_path.glob("year-long-project-team-*"))
    
    if not team_folders:
        print(f"No team folders found in '{base_path}'")
        return
    
    print(f"[INFO] Found {len(team_folders)} team folder(s)")
    
    # STEP 1: Enrich files
    print("\n" + "="*70)
    print("STEP 1: ENRICHING FILES")
    print("="*70)
    
    for team_folder in team_folders:
        print(f"\n{'='*70}")
        print(f"[INFO] Processing: {team_folder.name}")
        print(f"{'='*70}")
        
        enrich_prs_and_comments(team_folder)
    
    print(f"\n{'='*70}")
    print("[COMPLETE] All files enriched")
    print(f"{'='*70}")
    
    # STEP 2: Generate labels
    print("\n" + "="*70)
    print("STEP 2: GENERATING LABELS")
    print("="*70)
    
    for team_folder in sorted(team_folders):
        team_name = team_folder.name
        print(f"\n{'='*60}")
        print(f"[INFO] Starting label generation for {team_name}")
        print(f"{'='*60}")
        
        # Define paths for the team's data
        team_folder_path = team_folder
        prs_path = next((f for f in team_folder_path.glob("*.csv") if f.name.endswith("_all_pull_requests.csv")), None)
        commits_path = next((f for f in team_folder_path.glob("*.csv") if f.name.endswith("_PR_commits.csv")), None)
        commit_file_changes_path = next((f for f in team_folder_path.glob("*.csv") if f.name.endswith("_commit_file_changes.csv")), None)
        
        if not all([prs_path, commits_path, commit_file_changes_path]):
            print(f"[WARN] Missing one or more required files for label generation for {team_name}. Skipping.")
            continue
            
        print("[INFO] Loading PRs, Commits, and Commit File Changes...")
        prs_df = pd.read_csv(prs_path)
        commits_df = pd.read_csv(commits_path)
        commit_file_changes_df = pd.read_csv(commit_file_changes_path)
        
        # --- Pre-processing for all labelers ---
        # 1. Bot Removal (use centralized utilities)
        print("[INFO] Filtering bot PRs and commits using botFilter utilities...")

        # PRs: prefer convenience wrapper which expects 'pr_author' column
        try:
            prs_df = remove_bot_prs(prs_df)
        except KeyError:
            # Column missing, skip PR bot filtering but warn
            print("[WARN] 'pr_author' column not found in PRs DataFrame; skipping PR bot filtering")

        # Commits: use convenience wrapper which expects 'author' column
        try:
            commits_df = remove_bot_commits(commits_df)
        except KeyError:
            print("[WARN] 'author' column not found in commits DataFrame; skipping commit bot filtering")

        # Commit file changes: try to filter by 'author' if present, otherwise try multiple columns
        try:
            commit_file_changes_df = remove_bot_commits(commit_file_changes_df)
        except KeyError:
            # If 'author' not present, but multiple possible username columns exist, try filtering across them
            possible_username_cols = [c for c in ['author', 'committer', 'username'] if c in commit_file_changes_df.columns]
            if possible_username_cols:
                try:
                    commit_file_changes_df = filter_bots_from_multiple_columns(
                        commit_file_changes_df,
                        username_columns=possible_username_cols,
                        filter_mode='any'
                    )
                except KeyError as e:
                    print(f"[WARN] Bot filtering skipped for commit file changes: {e}")
            else:
                print("[WARN] No username-like columns found in commit file changes; skipping bot filtering for file changes")

        print(f"[INFO] After filtering - PRs: {len(prs_df)}, Commits: {len(commits_df)}, File Changes: {len(commit_file_changes_df)}")
        
        # 2. Anonymization (if enabled)
        if ANONYMIZE:
            print("[INFO] Applying anonymization (dynamic mapping load)")
            for col in ["pr_author", "merged_by", "head_branch"]:
                if col in prs_df.columns:
                    if col == "head_branch":
                        # anonymize_branch_names will load the mapping if none provided
                        prs_df[col] = anonymize_branch_names(prs_df[col])
                    else:
                        prs_df[col] = anonymize_column(prs_df[col])
        
        # 3. Create timestamp lookup for PR creation times
        pr_created_at_lookup = {}
        for _, row in prs_df.iterrows():
            pr_id = row.get("pr_id")
            created_at = row.get("created_at")
            if pd.notna(pr_id) and pd.notna(created_at):
                pr_created_at_lookup[pr_id] = created_at
        print(f"[INFO] Created timestamp lookup for {len(pr_created_at_lookup)} PRs")

        # 4. Prepare commits data with branch names (if available)
        if 'branch_name' in commits_df.columns:
            print("[INFO] Branch names found in commits data")
            commits_with_branch_df = commits_df[['pr_id', 'commit_sha', 'branch_name']].drop_duplicates(subset=['commit_sha'])
            
            # Merge branch name into commit_file_changes if it doesn't already have it
            if 'branch_name' not in commit_file_changes_df.columns:
                commit_file_changes_df = commit_file_changes_df.merge(
                    commits_with_branch_df,
                    on=['pr_id', 'commit_sha'], 
                    how='left'
                )
        else:
            print("[INFO] No branch_name column in commits data - will work without it")
        
        # --- Initialize List of all Labels ---
        all_labels_dfs = []
        
        # --- LABELING ---
        
        # 1. Branch Naming Labels (Meaningful/Random)
        branch_name_labels_df, llm_reasoning_df = label_branch_names(prs_df, ask_llm, RUN_TIMESTAMP)
        all_labels_dfs.append(branch_name_labels_df)

        # 2. Features Per Branch (One/Multiple)
        features_per_branch_df = label_features_per_branch(prs_df, RUN_TIMESTAMP)
        all_labels_dfs.append(features_per_branch_df)

        # 3/4. Feature & Refactor Size (Per file)
        required_file_cols = {"file_path", "lines_added", "lines_deleted", "pr_id", "commit_sha"}
        missing_cols = required_file_cols - set(commit_file_changes_df.columns)
        if missing_cols:
            print(f"[WARN] commit_file_changes CSV missing required columns for per-file size labels: {sorted(missing_cols)}")
            print("[INFO] Skipping Feature Size and Refactor Size labeling for this team.")
        else:
            # Feature Size: files with additions and no deletions
            feature_size_df = label_feature_size(commit_file_changes_df, prs_df, pr_created_at_lookup, RUN_TIMESTAMP)
            all_labels_dfs.append(feature_size_df)

            # Refactor Size: files with any deletions
            refactor_size_df = label_refactor_size(commit_file_changes_df, prs_df, pr_created_at_lookup, RUN_TIMESTAMP)
            all_labels_dfs.append(refactor_size_df)
        
        # 5. Repository Status (up-to-date/outdated)
        repo_status_df = label_repo_status(prs_df, RUN_TIMESTAMP)
        all_labels_dfs.append(repo_status_df)
        
        # 6. PR Status (closed/still_open/merged)
        pr_status_df = label_pr_status(prs_df, RUN_TIMESTAMP)
        all_labels_dfs.append(pr_status_df)
        
        # 7. Merge State (no_merge/self_merge/reviewed_merge)
        merge_state_df = label_merge_state(prs_df)
        all_labels_dfs.append(merge_state_df)

        # --- COMBINE AND SAVE ---
        if not all_labels_dfs:
            print(f"[WARN] No labels generated for {team_name}.")
            continue
            
        combined_df = pd.concat(all_labels_dfs, ignore_index=True)
        combined_df = combined_df.sort_values(by=["pr_id", "created_at"]).reset_index(drop=True)
        
        diagnose_timestamp_issues(combined_df)

        # Define output paths
        output_dir = Path("data/graph_labels")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"{team_name}_labels_branching_and_structure.csv"
        reasoning_file = output_dir / f"{team_name}_llm_branch_name_reasoning.csv"

        # Save final files
        combined_df.to_csv(output_file, index=False)
        llm_reasoning_df.to_csv(reasoning_file, index=False)

        print("-" * 60)
        print(f"[SUCCESS] Final labels saved to: {output_file}")
        print(f"[SUCCESS] LLM reasoning saved to: {reasoning_file}")
        
        # Determine cleaned file path (default behavior of util puts it in a 'clean' subfolder)
        create_clean_branching_label_csv(str(output_file))
        print(f"[INFO] Total events generated: {len(combined_df)}")
        print("=" * 60)
        
    print("\n" + "="*70)
    print("[COMPLETE] All label generation finished successfully!")
    print("="*70)

if __name__ == "__main__":
    process_all_teams()