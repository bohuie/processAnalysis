import os
import sys
import pandas as pd
import re
import json
import ast
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import utilities from src/utils
from src.utils.ollama_offline import connect_ollama_offline
from src.utils.label_merge import label_merge_state
from src.utils.anonymize_data import anonymize_username
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

# === SETUP ============================================================
MODEL_NAME = "llama3.2:3b"
RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"
ANONYMIZE = True

ask_llm = connect_ollama_offline

# === FILE ENRICHMENT AND CLEANING =====================================
def extract_username(value):
    """Extract username if cell looks like a dict, otherwise return original."""
    if pd.isna(value):
        return value
    val = str(value).strip()
    if val.startswith("{") and "username" in val:
        try:
            parsed = ast.literal_eval(val)
            if isinstance(parsed, dict) and "username" in parsed:
                return parsed["username"]
        except Exception:
            pass
    return val

# `get_top_file_info_single` removed — replaced by utilities in `src.utils.enrich_columns`
# Use `add_top_file_metrics` / `add_docs_updated_flag` from `src.utils.enrich_columns` instead.

def clean_review_comments(team_folder):
    """Clean review-comments.csv files by extracting usernames from dict format."""
    review_comment_files = [f for f in team_folder.glob("*.csv") if f.name.endswith("_review-comments.csv")]
    if not review_comment_files:
        print(f"[WARN] No review-comments.csv found in {team_folder}")
        return

    for file_path in review_comment_files:
        print(f"\n[INFO] Cleaning: {file_path}")

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            print(f"[ERROR] Failed to read {file_path}: {e}")
            continue

        if "author" not in df.columns:
            print("[WARN] 'author' column not found — skipping.")
            continue

        before_sample = df["author"].head(3).tolist()
        df["author"] = df["author"].apply(extract_username)
        after_sample = df["author"].head(3).tolist()

        print(f"[INFO] Sample before → after:")
        for b, a in zip(before_sample, after_sample):
            print(f"   {b}  →  {a}")

        if "created_at" in df.columns:
            print("[INFO] Converting 'created_at' to UTC Z format (if needed)...")
            df["created_at"] = df["created_at"].apply(
                lambda x: pd.to_datetime(x, errors='coerce', utc=True).strftime('%Y-%m-%dT%H:%M:%SZ')
                if pd.notna(x) and not str(x).endswith("Z") else x
            )

        try:
            df.to_csv(file_path, index=False)
            print(f"[SUCCESS] Overwritten cleaned file: {file_path}")
        except Exception as e:
            print(f"[ERROR] Could not save {file_path}: {e}")

def enrich_prs_and_comments(team_folder):
    """Enrich PRs with top file metrics and add order_of_review to comments using utility functions."""
    # Call the utility functions that handle all the enrichment
    add_top_file_metrics(team_folder)
    add_docs_updated_flag(team_folder)
    add_order_of_review(team_folder)

# === BRANCH NAME PROCESSING ===========================================
def get_unique_branch_names(prs_df):
    """Extract unique branch names regardless of PR ID presence."""
    if "head_branch" not in prs_df.columns:
        print("    No 'head_branch' column found in PR data")
        return []
    
    branch_names = prs_df["head_branch"].dropna().unique()
    branch_names = [str(branch).strip() for branch in branch_names if str(branch).strip()]
    
    print(f"    Found {len(branch_names)} unique branch names")
    return branch_names

def create_branch_struct(prs_df):
    """Create a mapping of branch names to their PR IDs and authors."""
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
    
    multi_pr_branches = {branch: prs for branch, prs in branch_mapping.items() if len(prs) > 1}
    if multi_pr_branches:
        print(f"    Found {len(multi_pr_branches)} branches used by multiple PRs")
        for branch, prs in list(multi_pr_branches.items())[:5]:
            print(f"      '{branch}': {len(prs)} PRs")
    
    return branch_mapping

# === ANONYMIZATION ====================================================
def load_anonymization_mapping():
    """Load anonymization mapping from JSON file."""
    mapping_path = "../confidential/anonymized_usernames.json"
    if os.path.exists(mapping_path):
        try:
            with open(mapping_path, 'r') as f:
                mapping = json.load(f)
            print(f"Loaded anonymization mapping from {mapping_path}")
            return mapping
        except Exception as e:
            print(f"Failed to load anonymization mapping: {e}")
            return {}
    else:
        print(f"Anonymization mapping file not found: {mapping_path}")
        print("   Please create a JSON file with real_name -> anonymized_name mapping")
        return {}

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
    """Anonymize branch names by replacing username parts within the full branch string."""
    if not mapping:
        return series
    
    s = series.astype(str)
    for real_name, anon in mapping.items():
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, anon, regex=True)
    return s

# === BRANCHING LABELING FUNCTIONS ======================================
def label_features_per_branch(prs_df):
    """Label: one, multiple - Counts how many features (PRs) were created per branch."""
    result_rows = []
    
    branch_mapping = create_branch_struct(prs_df)
    
    for branch_name, pr_list in branch_mapping.items():
        count = len(pr_list)
        
        event = "one Features Per Branch" if count == 1 else "multiple Features Per Branch"
        
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
    """Ask Ollama if the branch name is meaningful based on PR context.
    
    Returns:
        tuple: (label, reason, confidence_score, llm_output)
        - label: "Meaningful Branch Name" or "Random Branch Name"
        - reason: The LLM's reasoning for the decision
        - confidence_score: A score from 0-100 indicating confidence
        - llm_output: The full raw output from the LLM
    """
    prompt = f"""
        You are assessing whether this Git branch name clearly reflects the PR purpose.

        Branch name: {branch_name}
        PR title: {pr_title}
        PR description: {pr_description}

        Please provide your assessment in the following format:
        
        REASON: [Your reasoning explaining why the branch name is meaningful or random]
        PREDICTION: [Either "meaningful" or "random"]
        CONFIDENCE: [A number from 0-100 indicating how confident you are in your prediction]

        Guidelines:
        - If the branch name clearly relates to the feature, fix, or topic (e.g., 'feature/login', 'fix/navbar', 'refactor_api'), it is "meaningful".
        - If it is generic, unclear, random, or unrelated (e.g., 'test', 'final', 'update', 'misc', 'main', 'newbranch'), it is "random".
        - Confidence should be high (80-100) when the branch name clearly matches or clearly doesn't match the PR purpose.
        - Confidence should be lower (50-79) when there's some ambiguity.
        - Confidence should be very low (0-49) only when you're very uncertain.
    """
    llm_output = ask_llm(prompt).strip()
    
    # Parse the response to extract reason, prediction, and confidence
    reason = ""
    prediction = ""
    confidence_score = None
    
    # Try to extract REASON
    reason_match = re.search(r'REASON:\s*(.+?)(?=PREDICTION:|CONFIDENCE:|$)', llm_output, re.IGNORECASE | re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip()
    
    # Try to extract PREDICTION
    prediction_match = re.search(r'PREDICTION:\s*(meaningful|random)', llm_output, re.IGNORECASE)
    if prediction_match:
        prediction = prediction_match.group(1).lower()
    else:
        # Fallback: check if "meaningful" or "random" appears in the output
        answer = llm_output.lower()
        if "meaningful" in answer:
            prediction = "meaningful"
        else:
            prediction = "random"
    
    # Try to extract CONFIDENCE score
    confidence_match = re.search(r'CONFIDENCE:\s*(\d+)', llm_output, re.IGNORECASE)
    if confidence_match:
        try:
            confidence_score = int(confidence_match.group(1))
            # Clamp to 0-100 range
            confidence_score = max(0, min(100, confidence_score))
        except ValueError:
            confidence_score = None
    else:
        # Try to find any number in the confidence section
        confidence_section = re.search(r'CONFIDENCE:.*?(\d+)', llm_output, re.IGNORECASE | re.DOTALL)
        if confidence_section:
            try:
                confidence_score = int(confidence_section.group(1))
                confidence_score = max(0, min(100, confidence_score))
            except ValueError:
                confidence_score = None
    
    # If we couldn't extract reason, use a fallback
    if not reason:
        reason = "No explicit reason provided by LLM"
    
    # If we couldn't extract confidence, set a default based on prediction presence
    if confidence_score is None:
        confidence_score = 50  # Default to medium confidence if not found
    
    # Determine label
    if prediction == "meaningful":
        label = "Meaningful Branch Name"
    else:
        label = "Random Branch Name"

    return label, reason, confidence_score, llm_output

def label_branch_names(prs_df):
    """Label: meaningful, random - Uses LLM to determine if branch names are descriptive.
    
    For each branch, collects ALL pr_titles and pr_descriptions that belong to it,
    then passes them all to the LLM for assessment.
    """
    print("  Evaluating branch naming via Ollama...")
    result_rows = []
    llm_reasoning_rows = []

    branch_mapping = create_branch_struct(prs_df)
    unique_branches = get_unique_branch_names(prs_df)
    
    if not unique_branches:
        print("    No branch names found to evaluate")
        return pd.DataFrame(), pd.DataFrame()

    # Build comprehensive context for each branch: all PRs and their info
    branch_pr_info = {}
    for branch_name, pr_list in branch_mapping.items():
        pr_titles = []
        pr_descriptions = []
        
        for pr_info in pr_list:
            pr_id = pr_info["pr_id"]
            pr_row = prs_df[prs_df["pr_id"] == pr_id]
            if not pr_row.empty:
                pr_row = pr_row.iloc[0]
                title = str(pr_row.get("pr_title", "")).strip()
                description = str(pr_row.get("pr_description", "")).strip()
                
                if title:
                    pr_titles.append(title)
                if description:
                    pr_descriptions.append(description)
        
        branch_pr_info[branch_name] = {
            "pr_titles": pr_titles,
            "pr_descriptions": pr_descriptions,
            "pr_count": len(pr_list)
        }

    for branch_name in tqdm(unique_branches, desc="  Branch naming"):
        if branch_name.lower() in ["main", "master"]:
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

        # Get all PR titles and descriptions for this branch
        pr_titles = branch_pr_info[branch_name]["pr_titles"]
        pr_descriptions = branch_pr_info[branch_name]["pr_descriptions"]
        pr_count = branch_pr_info[branch_name]["pr_count"]
        
        # Combine all titles and descriptions into a single context
        all_pr_context = f"PR Count: {pr_count}\n"
        if pr_titles:
            all_pr_context += f"PR Titles:\n" + "\n".join(f"  - {title}" for title in pr_titles) + "\n"
        if pr_descriptions:
            all_pr_context += f"PR Descriptions:\n" + "\n".join(f"  - {desc}" for desc in pr_descriptions) + "\n"

        name_label, reason, confidence_score, llm_raw = assess_branch_meaningfulness(
            branch_name, all_pr_context, ""
        )
        
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
                    "pr_titles": " | ".join(pr_titles),
                    "pr_descriptions": " | ".join(pr_descriptions),
                    "pr_count": pr_count,
                    "branch_naming_label": name_label,
                    "llm_reasoning": reason,
                    "llm_confidence_score": confidence_score,
                    "llm_full_output": llm_raw,
                    "llm_timestamp": RUN_TIMESTAMP
                })

    labels_df = pd.DataFrame(result_rows) if result_rows else pd.DataFrame()
    llm_reasoning_df = pd.DataFrame(llm_reasoning_rows) if llm_reasoning_rows else pd.DataFrame()

    return labels_df, llm_reasoning_df

# === FEATURE SIZE LABELING ============================================
def label_feature_size(commits_df, prs_df, pr_created_at_lookup):
    """Label: small, large - Features calculated PER COMMIT based on net new lines added."""
    result_rows = []
    
    for commit_sha, commit_group in commits_df.groupby("commit_sha"):
        if len(commit_group) == 0:
            continue
            
        first_row = commit_group.iloc[0]
        pr_id = first_row.get("pr_id")
        
        pr_info = prs_df[prs_df["pr_id"] == pr_id]
        if pr_info.empty:
            continue
        pr_info = pr_info.iloc[0]
        
        if "file_path" in commit_group.columns and commit_group["file_path"].notna().any():
            total_feature_lines = 0
            for _, file_row in commit_group.iterrows():
                if pd.isna(file_row.get("file_path")):
                    continue
                additions = file_row.get("lines_added", 0)
                deletions = file_row.get("lines_deleted", 0)
                
                if additions > deletions:
                    pure_additions = additions - deletions
                    total_feature_lines += pure_additions
        else:
            total_feature_lines = 0
        
        if total_feature_lines == 0:
            continue
        
        event = "Small Feature Size" if total_feature_lines < 50 else "Large Feature Size"
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

# === REFACTOR SIZE LABELING ===========================================
def label_refactor_size(commits_df, prs_df, pr_created_at_lookup):
    """Label: small, large - Refactors calculated PER FILE based on lines modified."""
    result_rows = []
    
    if "file_path" not in commits_df.columns:
        print("    [WARN] No 'file_path' column in commits data.")
        print("    [INFO] Make sure you're loading '*_commit_file_changes.csv'")
        print("    [INFO] Skipping refactor analysis.")
        return pd.DataFrame()
    
    for _, row in commits_df.iterrows():
        pr_id = row.get("pr_id")
        commit_sha = row.get("commit_sha")
        filename = row.get("file_path", "unknown")
        
        additions = row.get("lines_added", 0)
        deletions = row.get("lines_deleted", 0)
        
        if additions == 0 and deletions == 0:
            continue
        
        pr_info = prs_df[prs_df["pr_id"] == pr_id]
        if pr_info.empty:
            continue
        pr_info = pr_info.iloc[0]
        
        refactor_lines = deletions + additions
        event = "Small Refactor Size" if refactor_lines < 50 else "Large Refactor Size"
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

# === REPOSITORY STATUS LABELING =======================================
def label_repo_status(prs_df: pd.DataFrame) -> pd.DataFrame:
    """Label: up-to-date, outdated - Determines if PR branch was up-to-date with base."""
    result_rows = []

    if "was_up_to_date_at_merge" not in prs_df.columns:
        print("Column 'was_up_to_date_at_merge' not found in dataframe.")
        return pd.DataFrame()

    print("Generating repository status labels based on 'was_up_to_date_at_merge'...")

    for _, row in prs_df.iterrows():
        pr_id = row.get("pr_id")
        was_up_to_date = row.get("was_up_to_date_at_merge", None)

        if isinstance(was_up_to_date, str):
            was_up_to_date = was_up_to_date.strip().lower()
            if was_up_to_date == "true":
                was_up_to_date = True
            elif was_up_to_date == "false":
                was_up_to_date = False
            else:
                was_up_to_date = None

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

    print(f"Generated {len(result_rows)} repository status labels")

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()

# === PR STATUS LABELING ===============================================
def label_pr_status(prs_df):
    """Label: closed, still_open, merged - Determines current status of the PR."""
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        state = row.get("state", "")
        merged_at = row.get("merged_at", None)
        
        if pd.isna(state):
            state = ""
        else:
            state = str(state).lower()
        
        if state == "open":
            event = "still_open"
            llm_output = "rule-based: currently open"
        elif state == "closed":
            event = "closed"
            llm_output = "rule-based: closed without merge"
        else:
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

# `label_merge_state` is provided by `src.utils.label_merge` and imported at module top.
# Using the utility implementation instead of the local duplicate.

def diagnose_timestamp_issues(df):
    """Check for timestamp issues in the final dataframe."""
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
    
    # STEP 1: Clean review comments and enrich files
    print("\n" + "="*70)
    print("STEP 1: CLEANING AND ENRICHING FILES")
    print("="*70)
    
    for team_folder in team_folders:
        print(f"\n{'='*70}")
        print(f"[INFO] Processing: {team_folder.name}")
        print(f"{'='*70}")
        
        clean_review_comments(team_folder)
        enrich_prs_and_comments(team_folder)
    
    print(f"\n{'='*70}")
    print("[COMPLETE] All review comments cleaned and files enriched")
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
        if ANONYMIZE and name_map:
            print("[INFO] Applying anonymization...")
            for col in ["pr_author", "merged_by", "head_branch"]:
                if col in prs_df.columns:
                    if col == "head_branch":
                        prs_df[col] = anonymize_branch_names(prs_df[col], name_map)
                    else:
                        prs_df[col] = anonymize_column(prs_df[col], name_map)
        
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
        branch_name_labels_df, llm_reasoning_df = label_branch_names(prs_df)
        all_labels_dfs.append(branch_name_labels_df)

        # 2. Features Per Branch (One/Multiple)
        features_per_branch_df = label_features_per_branch(prs_df)
        all_labels_dfs.append(features_per_branch_df)

        # 3. Feature Size (Small/Large) - Per Commit
        feature_size_df = label_feature_size(commit_file_changes_df, prs_df, pr_created_at_lookup)
        all_labels_dfs.append(feature_size_df)

        # 4. Refactor Size (Small/Large) - Per File in Commit
        refactor_size_df = label_refactor_size(commit_file_changes_df, prs_df, pr_created_at_lookup)
        all_labels_dfs.append(refactor_size_df)
        
        # 5. Repository Status (up-to-date/outdated)
        repo_status_df = label_repo_status(prs_df)
        all_labels_dfs.append(repo_status_df)
        
        # 6. PR Status (closed/still_open/merged)
        pr_status_df = label_pr_status(prs_df)
        all_labels_dfs.append(pr_status_df)
        
        # 7. Merge State (no_merge/self_merge/reviewed_merge)
        merge_state_df = label_merge_state(prs_df)
        all_labels_dfs.append(merge_state_df)

        # --- COMBINE AND SAVE ---
        if not all_labels_dfs:
            print(f"[WARN] No labels generated for {team_name}.")
            continue
            
        combined_df = pd.concat(all_labels_dfs, ignore_index=True)        
        # Normalize and sort final output
        # Convert timestamps to UTC Z format if needed
        combined_df["created_at"] = combined_df["created_at"].apply(
            lambda x: pd.to_datetime(x, errors='coerce', utc=True).strftime('%Y-%m-%dT%H:%M:%SZ')
            if pd.notna(x) and not str(x).endswith("Z") else x
        )
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
        print(f"[INFO] Total events generated: {len(combined_df)}")
        print("=" * 60)
        
    print("\n" + "="*70)
    print("[COMPLETE] All label generation finished successfully!")
    print("="*70)

if __name__ == "__main__":
    process_all_teams()