import os
import time
import pandas as pd
import numpy as np
import glob
import re
import json
from tqdm import tqdm
import ollama
from datetime import datetime, timezone
from dateutil import parser as date_parser

# === SETUP ============================================================
MODEL_NAME = "llama3.2:3b"
RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"


def normalize_timestamp_to_utc_z(timestamp_str):
    """Convert any timestamp format to UTC with Z suffix."""
    if pd.isna(timestamp_str) or timestamp_str == '' or timestamp_str is None:
        return None
    try:
        dt = date_parser.parse(str(timestamp_str))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    except:
        return timestamp_str


# === TIMESTAMP FIX FUNCTION ===========================================
def adjust_merge_timestamps(combined_df):
    """
    Fix chronological ordering by making merge events occur after the last commit.
    """
    print("  🔧 Adjusting merge event timestamps for chronological ordering...")
    
    combined_df["created_at"] = pd.to_datetime(combined_df["created_at"], utc=True, errors="coerce")
    
    # Only adjust "Merge State" events
    merge_mask = (combined_df["main_label"] == "Merge State")
    
    # Find last commit/refactor timestamp per PR (both are code change events)
    commit_events = ["Feature Size", "Refactor Size"]
    
    pr_last_commit_times = {}
    for pr_id in combined_df["pr_id"].unique():
        pr_commits = combined_df[
            (combined_df["pr_id"] == pr_id) & 
            (combined_df["main_label"].isin(commit_events))
        ]
        if not pr_commits.empty:
            pr_last_commit_times[pr_id] = pr_commits["created_at"].max()
    
    adjusted_count = 0
    for idx in combined_df[merge_mask].index:  # Iterate over index directly
        row = combined_df.loc[idx]
        pr_id = row["pr_id"]
        
        # PRIORITY 1: Use merged_at if available
        merged_at = row.get("merged_at")
        if pd.notna(merged_at):
            combined_df.at[idx, "created_at"] = pd.to_datetime(merged_at, utc=True)
            adjusted_count += 1
        # PRIORITY 2: Use last commit time + 1 second
        elif pr_id in pr_last_commit_times:
            new_timestamp = pr_last_commit_times[pr_id] + pd.Timedelta(seconds=1)
            combined_df.at[idx, "created_at"] = new_timestamp
            adjusted_count += 1
    
    print(f"    ✅ Adjusted {adjusted_count} merge event timestamps")
    return combined_df

# === BRANCH NAME PROCESSING ===========================================
def get_unique_branch_names(prs_df):
    """
    Extract unique branch names regardless of PR ID presence.
    Handles cases where branch names might be duplicated across PRs.
    """
    if "head_branch" not in prs_df.columns:
        print("    ⚠️ No 'head_branch' column found in PR data")
        return []
    
    # Get all branch names, handling NaN values
    branch_names = prs_df["head_branch"].dropna().unique()
    
    # Convert to string and filter out empty strings
    branch_names = [str(branch).strip() for branch in branch_names if str(branch).strip()]
    
    print(f"    📋 Found {len(branch_names)} unique branch names")
    return branch_names


def get_branch_pr_mapping(prs_df):
    """
    Create a mapping of branch names to their PR IDs and authors.
    Handles cases where multiple PRs might use the same branch name.
    """
    branch_mapping = {}
    
    if "head_branch" not in prs_df.columns or "pr_id" not in prs_df.columns:
        return branch_mapping
    
    for _, row in prs_df.iterrows():
        branch_name = str(row.get("head_branch", "")).strip()
        pr_id = row.get("pr_id")
        pr_author = row.get("pr_author", "unknown")
        created_at = row.get("created_at")
        
        if not branch_name or pd.isna(pr_id):
            continue
            
        if branch_name not in branch_mapping:
            branch_mapping[branch_name] = []
        
        branch_mapping[branch_name].append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": created_at
        })
    
    # Log branches with multiple PRs
    multi_pr_branches = {branch: prs for branch, prs in branch_mapping.items() if len(prs) > 1}
    if multi_pr_branches:
        print(f"    🔍 Found {len(multi_pr_branches)} branches used by multiple PRs")
        for branch, prs in list(multi_pr_branches.items())[:5]:  # Show first 5 examples
            print(f"      '{branch}': {len(prs)} PRs")
    
    return branch_mapping


# === ANONYMIZATION CONFIG =============================================
ANONYMIZE = True

def load_anonymization_mapping():
    """Load anonymization mapping from JSON file."""
    mapping_path = "../../confidential/anonymized_usernames.json"
    if os.path.exists(mapping_path):
        try:
            with open(mapping_path, 'r') as f:
                mapping = json.load(f)
            print(f"✅ Loaded anonymization mapping from {mapping_path}")
            return mapping
        except Exception as e:
            print(f"❌ Failed to load anonymization mapping: {e}")
            return {}
    else:
        print(f"❌ Anonymization mapping file not found: {mapping_path}")
        print("   Please create a JSON file with real_name -> anonymized_name mapping")
        return {}

# Load the mapping
name_map = load_anonymization_mapping()


def anonymize_column(series: pd.Series, mapping: dict) -> pd.Series:
    """Replace exact matches or substrings based on mapping (case-insensitive)."""
    if not mapping:
        return series
    
    s = series.astype(str)
    for real_name, anon in mapping.items():
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, anon, regex=True)
    return s


def anonymize_branch_names(series: pd.Series, mapping: dict) -> pd.Series:
    """
    Anonymize branch names by replacing username parts within the full branch string.
    """
    if not mapping:
        return series
    
    s = series.astype(str)
    for real_name, anon in mapping.items():
        # Case-insensitive pattern to match the username anywhere in the branch name
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, anon, regex=True)
    return s


# === HELPER: Send prompt to Ollama ======================================
def ask_ollama(prompt: str) -> str:
    """Send a text classification prompt to Ollama running locally."""
    while True:
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a concise text classifier."},
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0.2,
                    "num_predict": 200,
                }
            )
            return response['message']['content'].strip()
        except Exception as e:
            err = str(e)
            print(f"⚠️ Ollama error: {err} — retrying in 3 seconds...")
            time.sleep(3)


# === BRANCHING LABELING FUNCTIONS ======================================

def label_features_per_branch(prs_df):
    """
    Label: one, multiple
    Counts how many features (PRs) were created per branch.
    Uses unique branch names regardless of PR ID.
    """
    result_rows = []
    
    # Get branch mapping to handle branches with multiple PRs
    branch_mapping = get_branch_pr_mapping(prs_df)
    
    for branch_name, pr_list in branch_mapping.items():
        count = len(pr_list)
        
        event = "one Features Per Branch" if count == 1 else "multiple Features Per Branch"
        
        # Create an event for each PR associated with this branch
        for pr_info in pr_list:
            result_rows.append({
                "pr_id": pr_info["pr_id"],
                "pr_author": pr_info["pr_author"],
                "created_at": pr_info.get("created_at"),
                "branch_name": branch_name,
                "event": event,
                "main_label": "Features Per Branch",
                "llm_output": f"rule-based: {count} feature(s) on branch '{branch_name}'",
                "llm_timestamp": RUN_TIMESTAMP
            })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()


def assess_branch_meaningfulness(branch_name, pr_title, pr_description):
    """Ask Ollama if the branch name is meaningful based on PR context."""
    prompt = f"""
        You are assessing whether this Git branch name clearly reflects the PR purpose.

        Branch name: {branch_name}
        PR title: {pr_title}
        PR description: {pr_description}

        If the branch name clearly relates to the feature, fix, or topic (e.g., 'feature/login', 'fix/navbar', 'refactor_api'),
        respond with ONLY: "meaningful".
        If it is generic, unclear, random, or unrelated (e.g., 'test', 'final', 'update', 'misc', 'main', 'newbranch'),
        respond with ONLY: "random".
    """
    llm_output = ask_ollama(prompt).strip()
    answer = llm_output.lower()

    if "meaningful" in answer:
        label = "Meaningful Branch Name"
    else:
        label = "Random Branch Name"

    return label, llm_output


def label_branch_names(prs_df):
    """
    Label: meaningful, random
    Uses LLM to determine if branch names are descriptive.
    Processes unique branch names regardless of PR ID.
    """
    print("  Evaluating branch naming via Ollama...")
    result_rows = []
    llm_reasoning_rows = []

    # Get unique branch names and their mapping to PRs
    branch_mapping = get_branch_pr_mapping(prs_df)
    unique_branches = get_unique_branch_names(prs_df)
    
    if not unique_branches:
        print("    ⚠️ No branch names found to evaluate")
        return pd.DataFrame(), pd.DataFrame()

    # Create a lookup for PR title and description by branch name
    # Use the first PR's context for each branch to avoid duplicate LLM calls
    branch_context = {}
    for branch_name, pr_list in branch_mapping.items():
        if pr_list:
            first_pr = pr_list[0]
            pr_id = first_pr["pr_id"]
            # Find the PR row to get title and description
            pr_row = prs_df[prs_df["pr_id"] == pr_id]
            if not pr_row.empty:
                pr_row = pr_row.iloc[0]
                branch_context[branch_name] = {
                    "pr_title": str(pr_row.get("pr_title", "")),
                    "pr_description": str(pr_row.get("pr_description", ""))
                }

    for branch_name in tqdm(unique_branches, desc="  Branch naming"):
        # Auto-label main/master as random
        if branch_name.lower() in ["main", "master"]:
            # Create events for all PRs using this branch
            if branch_name in branch_mapping:
                for pr_info in branch_mapping[branch_name]:
                    result_rows.append({
                        "pr_id": pr_info["pr_id"],
                        "pr_author": pr_info["pr_author"],
                        "created_at": pr_info.get("created_at"),
                        "branch_name": branch_name,
                        "event": "Random Branch Name",
                        "main_label": "Branch Name",
                        "llm_output": "auto-labeled: main/master branch",
                        "llm_timestamp": RUN_TIMESTAMP
                    })
            continue

        # Get PR context for this branch
        pr_title = ""
        pr_description = ""
        if branch_name in branch_context:
            pr_title = branch_context[branch_name]["pr_title"]
            pr_description = branch_context[branch_name]["pr_description"]

        name_label, llm_raw = assess_branch_meaningfulness(
            branch_name, pr_title, pr_description
        )
        
        # Create events for all PRs using this branch
        if branch_name in branch_mapping:
            for pr_info in branch_mapping[branch_name]:
                result_rows.append({
                    "pr_id": pr_info["pr_id"],
                    "pr_author": pr_info["pr_author"],
                    "created_at": pr_info.get("created_at"),
                    "branch_name": branch_name,
                    "event": name_label,
                    "main_label": "Branch Name",
                    "llm_output": llm_raw,
                    "llm_timestamp": RUN_TIMESTAMP
                })
                
                llm_reasoning_rows.append({
                    "pr_id": pr_info["pr_id"],
                    "pr_author": pr_info["pr_author"],
                    "created_at": pr_info.get("created_at"),
                    "branch_name": branch_name,
                    "pr_title": pr_title,
                    "pr_description": pr_description,
                    "branch_naming_label": name_label,
                    "llm_reasoning": llm_raw,
                    "llm_timestamp": RUN_TIMESTAMP
                })

    labels_df = pd.DataFrame(result_rows) if result_rows else pd.DataFrame()
    llm_reasoning_df = pd.DataFrame(llm_reasoning_rows) if llm_reasoning_rows else pd.DataFrame()

    return labels_df, llm_reasoning_df


# === FEATURE SIZE LABELING (PER COMMIT) ================================

def label_feature_size(commits_df, prs_df, pr_created_at_lookup):
    """
    Label: small, large
    Features are calculated PER COMMIT based on net new lines added.
    
    FIXED: Uses 'lines_added' and 'lines_deleted' from commit file changes data.
    """
    result_rows = []
    
    # Group by commit to process each commit separately
    for commit_sha, commit_group in commits_df.groupby("commit_sha"):
        if len(commit_group) == 0:
            continue
            
        first_row = commit_group.iloc[0]
        pr_id = first_row.get("pr_id")
        
        # Get PR metadata
        pr_info = prs_df[prs_df["pr_id"] == pr_id]
        if pr_info.empty:
            continue
        pr_info = pr_info.iloc[0]
        
        # Calculate feature size for this commit
        if "file_path" in commit_group.columns and commit_group["file_path"].notna().any():
            total_feature_lines = 0
            for _, file_row in commit_group.iterrows():
                if pd.isna(file_row.get("file_path")):
                    continue  # Skip rows without file data
                # FIX: Use correct column names
                additions = file_row.get("lines_added", 0)
                deletions = file_row.get("lines_deleted", 0)
                
                # Feature lines = net new additions (when additions > deletions)
                if additions > deletions:
                    pure_additions = additions - deletions
                    total_feature_lines += pure_additions
        else:
            # Fallback: No file-level data
            total_feature_lines = 0
        
        # Skip commits with no feature work
        if total_feature_lines == 0:
            continue
        
        # Classify as small or large (threshold = 50 lines)
        event = "Small Feature Size" if total_feature_lines < 50 else "Large Feature Size"
        
        # Get created_at from lookup (guaranteed to exist due to early filter)
        created_at = pr_created_at_lookup.get(pr_id)
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_info["pr_author"],
            "created_at": created_at,
            "commit_sha": commit_sha,
            "event": event,
            "main_label": "Feature Size",
            "llm_output": f"rule-based: {total_feature_lines} feature lines (per commit)",
            "llm_timestamp": RUN_TIMESTAMP
        })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()


# === REFACTOR SIZE LABELING (PER FILE) ================================

def label_refactor_size(commits_df, prs_df, pr_created_at_lookup):
    """
    Label: small, large
    Refactors are calculated PER FILE based on lines modified (deleted + added).
    Only files with actual changes are included.
    """
    result_rows = []
    
    # Check if we have file-level data
    if "file_path" not in commits_df.columns:
        print("    [WARN] No 'file_path' column in commits data.")
        print("    [INFO] Make sure you're loading '*_commit_file_changes.csv' (not '*_PR_commits.csv')")
        print("    [INFO] Skipping refactor analysis.")
        return pd.DataFrame()
    
    # Process each file in each commit
    for _, row in commits_df.iterrows():
        pr_id = row.get("pr_id")
        commit_sha = row.get("commit_sha")
        filename = row.get("file_path", "unknown")
        
        additions = row.get("lines_added", 0)
        deletions = row.get("lines_deleted", 0)
        
        # Skip files with no changes (for both features AND refactors)
        if additions == 0 and deletions == 0:
            continue
        
        # Get PR metadata
        pr_info = prs_df[prs_df["pr_id"] == pr_id]
        if pr_info.empty:
            continue
        pr_info = pr_info.iloc[0]
        
        # Calculate refactor size: total lines modified
        refactor_lines = deletions + additions
        
        # Classify as small or large (threshold = 50 lines)
        event = "Small Refactor Size" if refactor_lines < 50 else "Large Refactor Size"
        
        # Get created_at from lookup
        created_at = pr_created_at_lookup.get(pr_id)
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_info["pr_author"],
            "created_at": created_at,
            "commit_sha": commit_sha,
            "filename": filename,
            "event": event,
            "main_label": "Refactor Size",
            "llm_output": f"rule-based: {refactor_lines} lines modified ({deletions}D+{additions}A) in {filename}",
            "llm_timestamp": RUN_TIMESTAMP
        })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()

# === REPOSITORY STATUS LABELING ========================================

def label_repo_status(prs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Label: up-to-date, outdated
    Determines if PR branch was up-to-date with base using the 'was_up_to_date_at_merge' column.
    
    Rules:
    - True  → "up-to-date"
    - False → "outdated"
    - NaN or missing → skip (no label created)
    """
    result_rows = []

    if "was_up_to_date_at_merge" not in prs_df.columns:
        print("⚠️ Column 'was_up_to_date_at_merge' not found in dataframe.")
        return pd.DataFrame()

    print("🔍 Generating repository status labels based on 'was_up_to_date_at_merge'...")

    for _, row in prs_df.iterrows():
        pr_id = row.get("pr_id")
        was_up_to_date = row.get("was_up_to_date_at_merge", None)

        # Normalize any string-like values to boolean
        if isinstance(was_up_to_date, str):
            was_up_to_date = was_up_to_date.strip().lower()
            if was_up_to_date == "true":
                was_up_to_date = True
            elif was_up_to_date == "false":
                was_up_to_date = False
            else:
                was_up_to_date = None

        # Skip if missing or invalid
        if pd.isna(was_up_to_date) or was_up_to_date is None:
            continue

        if was_up_to_date is True:
            event = "up-to-date"
            llm_output = "rule-based: was_up_to_date_at_merge=True"
        else:
            event = "outdated"
            conflicts = row.get("has_conflicts", "N/A")
            llm_output = f"rule-based: was_up_to_date_at_merge=False (conflicts={conflicts})"

        result_rows.append({
            "pr_id": pr_id,
            "pr_author": row.get("pr_author"),
            "created_at": row.get("created_at"),
            "event": event,
            "main_label": "Repository Status",
            "llm_output": llm_output,
            "llm_timestamp": RUN_TIMESTAMP
        })

    print(f"✅ Generated {len(result_rows)} repository status labels")

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()


# === PR STATUS LABELING ================================================

def label_pr_status(prs_df):
    """
    Label: closed, still_open, merged
    Determines current status of the PR with proper handling of merged state.
    
    Categories:
    - merged: PR was successfully merged (state may show as 'closed')
    - closed: PR was closed without merging
    - still_open: PR is currently open
    """
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        state = row.get("state", "")
        merged_at = row.get("merged_at", None)
        
        # Handle float/NaN values and convert to string
        if pd.isna(state):
            state = ""
        else:
            state = str(state).lower()
        
        # Determine PR status with priority on merged status
        if state == "open":
            event = "still_open"
            llm_output = "rule-based: currently open"
        elif state == "closed":
            event = "closed"
            llm_output = "rule-based: closed without merge"
        else:
            # Default to closed for unknown states
            event = "closed"
            llm_output = f"rule-based: unknown state '{state}', treating as closed"
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": row.get("created_at"),
            "event": event,
            "main_label": "PR Status",
            "llm_output": llm_output,
            "llm_timestamp": RUN_TIMESTAMP
        })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()

# === MERGE STATE LABELING ==============================================
def label_merge_state(prs_df):
    """
    Label: no_merge, self_merge, reviewed_merge
    Determines how the PR was merged (if at all).
    """
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        merged_at = row.get("merged_at")
        created_at = row.get("created_at")
        
        # Define merged_by for the current row
        merged_by_from_row = row.get("merged_by") # <--- FIX: Get the value here
        
        # 1. Determine merge state (checking merged_at is a safer proxy for merge status)
        if pd.isna(merged_at) or merged_at == '' or merged_at is None:
            event = "no_merge"
            llm_output = "rule-based: PR not merged"
        else:
            # 2. It was merged, now check *who* merged it
            merged_by = str(merged_by_from_row).strip()
            pr_author_str = str(pr_author).strip()
            
            # Use .lower() for robust, case-insensitive comparison
            if merged_by and pr_author_str and merged_by.lower() == pr_author_str.lower(): 
                # Same person merged their own PR
                event = "self_merge"
                llm_output = f"rule-based: self-merged by {pr_author}"
            else:
                # Merged by someone else (reviewed or otherwise)
                event = "reviewed_merge"
                merger_info = f"by {merged_by}" if merged_by else "(merger unknown)"
                llm_output = f"rule-based: merged {merger_info}"
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": created_at,
            "merged_at": merged_at,
            "event": event,
            "main_label": "Merge State",
            "llm_output": llm_output,
            "llm_timestamp": RUN_TIMESTAMP
        })
    
    return pd.DataFrame(result_rows)

def diagnose_merge_states(prs_df):
    """Print diagnostic information about merge states."""
    print("\n📊 MERGE STATE DIAGNOSTICS")
    print("="*60)
    
    total_prs = len(prs_df)
    
    # Check merged_at column
    if "merged_at" in prs_df.columns:
        merged_count = prs_df["merged_at"].notna().sum()
        print(f"  Total PRs: {total_prs}")
        print(f"  Merged PRs: {merged_count} ({merged_count/total_prs*100:.1f}%)")
        print(f"  Not merged: {total_prs - merged_count} ({(total_prs-merged_count)/total_prs*100:.1f}%)")
    else:
        print("  ⚠️  'merged_at' column not found")
    
    # Check self-merge
    if "is_self_merged" in prs_df.columns:
        self_merged = prs_df["is_self_merged"].apply(
            lambda x: str(x).lower() == 'true' if pd.notna(x) else False
        ).sum()
        print(f"  Self-merged: {self_merged}")
    
    # Check reviewers
    if "num_reviewers" in prs_df.columns:
        with_reviewers = prs_df["num_reviewers"].apply(
            lambda x: int(x) > 0 if pd.notna(x) else False
        ).sum()
        print(f"  With reviewers: {with_reviewers}")
    
    # Check state column
    if "state" in prs_df.columns:
        print("\n  PR States:")
        state_counts = prs_df["state"].value_counts()
        for state, count in state_counts.items():
            print(f"    {state}: {count} ({count/total_prs*100:.1f}%)")
    
    print("="*60)

# === DIAGNOSTIC HELPER =================================================

def diagnose_timestamp_issues(df):
    """Check for timestamp issues in the final dataframe."""
    missing = df["created_at"].isna().sum()
    total = len(df)
    
    if missing > 0:
        print(f"\n⚠️  WARNING: {missing}/{total} events have missing timestamps")
        
        # Show examples of missing timestamps
        missing_df = df[df["created_at"].isna()][["pr_id", "pr_author", "main_label", "event"]].head(10)
        if not missing_df.empty:
            print("  Examples of events with missing timestamps:")
            print(missing_df.to_string(index=False))
    else:
        print(f"\n✅ All {total} events have valid timestamps")


# === MAIN PROCESSING ===================================================

def process_all_teams():
    """Main function to process all teams."""
    base_path = "../../data/csv/"
    
    if not os.path.exists(base_path):
        print(f"❌ Base path '{base_path}' not found!")
        print(f"[INFO] Current working directory: {os.getcwd()}")
        print(f"[INFO] Please ensure data folder exists in the current directory")
        return
    
    team_folders = [
        d for d in glob.glob(os.path.join(base_path, "*"))
        if os.path.isdir(d)
    ]
    
    if not team_folders:
        print(f"❌ No team folders found in '{base_path}'")
        return
    
    for team_folder in sorted(team_folders):
        team_name = os.path.basename(team_folder)
        print(f"\n{'='*60}")
        print(f"Processing {team_name}...")
        print('='*60)

        prs_path = None
        for pattern in [
            f"{team_name}_all_pull_requests_fixed.csv",
            f"{team_name}_PRs.csv",
            f"{team_name}_pull_requests.csv",
            "all_pull_requests.csv"
        ]:
            potential_path = os.path.join(team_folder, pattern)
            if os.path.exists(potential_path):
                prs_path = potential_path
                break

        if not prs_path:
            print(f"❌ Missing PRs CSV for {team_name}, skipping.")
            continue

        commits_path = None
        for pattern in [
            f"{team_name}_commit_file_changes.csv",
            f"{team_name}_PR_commits_fixed.csv",
            f"{team_name}_commits.csv",
            "PR_commits.csv"
        ]:
            potential_path = os.path.join(team_folder, pattern)
            if os.path.exists(potential_path):
                commits_path = potential_path
                print(f"✅ Found commits file: {os.path.basename(potential_path)}")
                if "file_changes" in pattern:
                    print(f"   ℹ️  Using file-level commit data (best for granular analysis)")
                else:
                    print(f"   ⚠️  Using commit-level data (limited file-level detail)")
                break

        print(f"Loading PRs from: {os.path.basename(prs_path)}")
        prs_df = pd.read_csv(prs_path)
        
        # --- START FIX: BOT FILTERING FOR PRs ---
        bot_patterns_regex = [
            # Standard Bot Patterns
            r'\[bot\]$',         # Catches [bot] at the end, e.g., dependabot[bot]
            r'^bot[-_]',         # Catches bot-*, bot_*, e.g., bot-user
            r'[-_]bot',          # Catches *-bot, e.g., user-bot
            r'^bot\d',           # Catches bot1, bot2, etc.
            # Specific Bot Names
            r'dependabot',
            r'github-actions',
            r'renovate',
            r'greenkeeper',
            r'codecov',
            r'snyk-bot',
            # Explicitly add the problematic author: github-classroom[bot]
            r'github-classroom', 
        ]


        original_count = len(prs_df)
        if 'pr_author' in prs_df.columns:
            prs_df = prs_df[~prs_df['pr_author'].str.lower().str.contains(
                '|'.join(bot_patterns_regex), 
                na=False, 
                regex=True
            )]
            bots_filtered = original_count - len(prs_df)
            if bots_filtered > 0:
                print(f"[INFO] Filtered out {bots_filtered} bot PRs")
        # --- END FIX: BOT FILTERING FOR PRs ---
        
        # Normalize timestamps to UTC Z format
        if "created_at" in prs_df.columns:
            prs_df["created_at"] = prs_df["created_at"].apply(normalize_timestamp_to_utc_z)
        if "merged_at" in prs_df.columns:
            prs_df["merged_at"] = prs_df["merged_at"].apply(normalize_timestamp_to_utc_z)
            
        prs_df["created_at"] = pd.to_datetime(prs_df["created_at"], utc=True, errors="coerce")
        prs_df["merged_at"] = pd.to_datetime(prs_df["merged_at"], utc=True, errors="coerce")

        # FIX: Robustly filter out PRs with missing/invalid created_at before processing
        original_pr_count = len(prs_df)
        prs_df = prs_df.dropna(subset=["created_at"])
        if len(prs_df) < original_pr_count:
             print(f"[WARN] Dropped {original_pr_count - len(prs_df)} PRs due to missing/invalid 'created_at' timestamp. Only valid PRs will be labeled.")

        # CRITICAL: Create a lookup dictionary for created_at by pr_id
        pr_created_at_lookup = {}
        for _, row in prs_df.iterrows():
            pr_id = row.get("pr_id")
            created_at = row.get("created_at")
            if pd.notna(pr_id) and pd.notna(created_at):
                pr_created_at_lookup[pr_id] = created_at
        
        print(f"[INFO] Created timestamp lookup for {len(pr_created_at_lookup)} PRs")

        if "pr_author" not in prs_df.columns:
            if "author" in prs_df.columns:
                prs_df["pr_author"] = prs_df["author"]
            else:
                prs_df["pr_author"] = "unknown"

        # Get unique branch names for diagnostics
        unique_branches = get_unique_branch_names(prs_df)
        branch_mapping = get_branch_pr_mapping(prs_df)
        print(f"[INFO] Processing {len(unique_branches)} unique branch names across {len(prs_df)} PRs")

        if ANONYMIZE:
            if name_map:
                print(f"🔐 Anonymizing PR authors...")
                prs_df["pr_author"] = anonymize_column(prs_df["pr_author"], name_map)
                
                # Anonymize branch names
                if "head_branch" in prs_df.columns:
                    print(f"🔐 Anonymizing branch names...")
                    prs_df["head_branch"] = anonymize_branch_names(prs_df["head_branch"], name_map)
            else:
                print(f"⚠️  Anonymization enabled but no mapping loaded - skipping anonymization")

        commits_df = None
        if commits_path:
            print(f"Loading commits from: {os.path.basename(commits_path)}")
            commits_df = pd.read_csv(commits_path)
            
            # --- START FIX: BOT FILTERING FOR COMMITS ---
            bot_patterns_regex = [
            # Standard Bot Patterns
            r'\[bot\]$',         # Catches [bot] at the end, e.g., dependabot[bot]
            r'^bot[-_]',         # Catches bot-*, bot_*, e.g., bot-user
            r'[-_]bot',          # Catches *-bot, e.g., user-bot
            r'^bot\d',           # Catches bot1, bot2, etc.
            # Specific Bot Names
            r'dependabot',
            r'github-actions',
            r'renovate',
            r'greenkeeper',
            r'codecov',
            r'snyk-bot',
            # Explicitly add the problematic author: github-classroom[bot]
            r'github-classroom', 
            ]

            
            original_count = len(commits_df)
            if 'author' in commits_df.columns:
                commits_df = commits_df[~commits_df['author'].str.lower().str.contains(
                    '|'.join(bot_patterns_regex), 
                    na=False, 
                    regex=True
                )]
                bots_filtered = original_count - len(commits_df)
                if bots_filtered > 0:
                    print(f"[INFO] Filtered out {bots_filtered} bot commits")
            # --- END FIX: BOT FILTERING FOR COMMITS ---
            
            commits_df["commit_date"] = pd.to_datetime(commits_df.get("commit_date"), errors="coerce")

            if ANONYMIZE and "author" in commits_df.columns and name_map:
                print(f"🔐 Anonymizing commit authors...")
                commits_df["author"] = anonymize_column(commits_df["author"], name_map)
        else:
            print(f"⚠️  Warning: No commits CSV found for {team_name}")

        all_labels = []
        llm_reasoning_data = []

        # === CODE STRUCTURE / BRANCHING LABELS ===
        print("\n📊 Generating Code Structure / Branching Labels...")
        
        print("  - Features per branch (one, multiple)...")
        try:
            features_per_branch_labels = label_features_per_branch(prs_df.copy())
            if not features_per_branch_labels.empty:
                all_labels.append(features_per_branch_labels)
                print(f"    ✅ Generated {len(features_per_branch_labels)} events")
        except Exception as e:
            print(f"    ❌ Error: {e}")

        print("  - Branch names (meaningful, random)...")
        try:
            branch_name_labels, branch_name_reasoning = label_branch_names(prs_df.copy())
            if not branch_name_labels.empty:
                all_labels.append(branch_name_labels)
                print(f"    ✅ Generated {len(branch_name_labels)} events")
            if not branch_name_reasoning.empty:
                llm_reasoning_data.append(branch_name_reasoning)
        except Exception as e:
            print(f"    ❌ Error: {e}")

        if commits_df is not None:
            print("  - Feature size (small, large)...")
            try:
                feature_size_labels = label_feature_size(commits_df.copy(), prs_df.copy(), pr_created_at_lookup)
                if not feature_size_labels.empty:
                    all_labels.append(feature_size_labels)
                    print(f"    ✅ Generated {len(feature_size_labels)} events")
            except Exception as e:
                print(f"    ❌ Error: {e}")

            print("  - Refactor size (small, large)...")
            try:
                refactor_size_labels = label_refactor_size(commits_df.copy(), prs_df.copy(), pr_created_at_lookup)
                if not refactor_size_labels.empty:
                    all_labels.append(refactor_size_labels)
                    print(f"    ✅ Generated {len(refactor_size_labels)} events")
            except Exception as e:
                print(f"    ❌ Error: {e}")

        print("  - Repository status (up-to-date, outdated)...")
        try:
            repo_status_labels = label_repo_status(prs_df.copy())
            if not repo_status_labels.empty:
                all_labels.append(repo_status_labels)
                print(f"    ✅ Generated {len(repo_status_labels)} events")
        except Exception as e:
            print(f"    ❌ Error: {e}")

        print("  - PR status (closed, still_open)...")
        try:
            pr_status_labels = label_pr_status(prs_df.copy())
            if not pr_status_labels.empty:
                all_labels.append(pr_status_labels)
                print(f"    ✅ Generated {len(pr_status_labels)} events")
        except Exception as e:
            print(f"    ❌ Error: {e}")

        print("  - Merge state (no_merge, self-merge, reviewed_merge)...")
        try:
            merge_state_labels = label_merge_state(prs_df.copy())
            if not merge_state_labels.empty:
                all_labels.append(merge_state_labels)
                print(f"    ✅ Generated {len(merge_state_labels)} events")
        except Exception as e:
            print(f"    ❌ Error: {e}")

        if not all_labels:
            print(f"⚠️ No labels generated for {team_name}, continuing to next team.")
            continue

        combined = pd.concat(all_labels, ignore_index=True, sort=False)
        combined["created_at"] = pd.to_datetime(combined["created_at"], utc=True, errors="coerce")

        # === APPLY TIMESTAMP FIX FOR CHRONOLOGICAL ORDERING ===
        combined = adjust_merge_timestamps(combined)
        
        # Diagnostic check (Should show 0 missing timestamps)
        diagnose_timestamp_issues(combined)
        
        # Convert created_at to UTC Z string format for CSV output
        if "created_at" in combined.columns:
            combined["created_at"] = combined["created_at"].apply(
                lambda x: x.strftime('%Y-%m-%dT%H:%M:%SZ') if pd.notna(x) else ''
            )

        suffix = "_anonymized" if ANONYMIZE and name_map else ""
        
        graphs_folder = os.path.join(team_folder, "graphs")
        os.makedirs(graphs_folder, exist_ok=True)
        
        # Output file matching graphing.py naming convention
        out_path = os.path.join("../../data/csv/", f"code_structure_branching_labels_{team_name}{suffix}.csv")
        
        try:
            combined.to_csv(out_path, index=False)
            print(f"\n✅ Saved combined event labels to: {out_path}")
            
            if ANONYMIZE and name_map:
                print(f"🔐 Anonymized authors in output:")
                unique_authors = combined["pr_author"].unique()
                for author in sorted(unique_authors):
                    count = (combined["pr_author"] == author).sum()
                    print(f"   • {author}: {count} events")
        except Exception as e:
            print(f"❌ Failed to save labels to {out_path}: {e}")
        
        if llm_reasoning_data:
            reasoning_folder = os.path.join(team_folder, "graphs", "reasoning")
            os.makedirs(reasoning_folder, exist_ok=True)
            
            combined_llm = pd.concat(llm_reasoning_data, ignore_index=True, sort=False)
            combined_llm["created_at"] = pd.to_datetime(combined_llm["created_at"], utc=True, errors="coerce")
            
            # Convert created_at to UTC Z string format for CSV output
            if "created_at" in combined_llm.columns:
                combined_llm["created_at"] = combined_llm["created_at"].apply(
                    lambda x: x.strftime('%Y-%m-%dT%H:%M:%SZ') if pd.notna(x) else ''
                )
            
            llm_out_path = os.path.join(reasoning_folder, f"{team_name}_all_llm_reasoning{suffix}.csv")
            
            try:
                combined_llm.to_csv(llm_out_path, index=False)
                print(f"✅ Saved LLM reasoning data to: {llm_out_path}")
            except Exception as e:
                print(f"❌ Failed to save LLM reasoning to {llm_out_path}: {e}")

    print("\n" + "="*60)
    print("✅ ALL TEAMS PROCESSED")
    print("="*60)
    if ANONYMIZE and name_map:
        print("🔐 Anonymization was ENABLED for all outputs")
    elif ANONYMIZE and not name_map:
        print("⚠️  Anonymization was ENABLED but no mapping was loaded")
    else:
        print("🔐 Anonymization was DISABLED")
    print("="*60)


# === MAIN EXECUTION ====================================================
if __name__ == "__main__":
    process_all_teams()