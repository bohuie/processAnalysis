import os
import sys
import time
import pandas as pd
import numpy as np
import glob
import re
import json
import ast
from pathlib import Path
from tqdm import tqdm
import ollama
from datetime import datetime, timezone
from dateutil import parser as date_parser

from event_labelling.Utility.bot_filter import remove_bot_prs, remove_bot_commits

# === SETUP ============================================================
MODEL_NAME = "llama3.2:3b"
RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"
ANONYMIZE = True

# === TIMESTAMP NORMALIZATION ==========================================
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

# === FILE ENRICHMENT AND CLEANING =====================================
def clean_review_comments(team_folder):
    """Clean review-comments.csv files by extracting usernames from dict format."""
    review_comment_files = sorted(team_folder.glob("*_review-comments.csv"))
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
    """Enrich PRs with top file metrics and add order_of_review to comments."""
    team_name = team_folder.name
    print(f"\n{'='*70}")
    print(f"[INFO] Enriching data for: {team_name}")
    print(f"{'='*70}")

    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if re.search(r"_PR_commits\.csv$", f.name, re.IGNORECASE)), None)
    prs_path = next((f for f in all_csvs if re.search(r"_all_pull_requests\.csv$", f.name, re.IGNORECASE)), None)
    review_comments_path = next((f for f in all_csvs if re.search(r"_review-comments\.csv$", f.name, re.IGNORECASE)), None)

    if not all([commits_path, prs_path, review_comments_path]):
        print(f"[WARN] Missing one or more required files for {team_name}, skipping enrichment.")
        return

    print(f"[INFO] Loading input CSVs...")
    commits_df = pd.read_csv(commits_path)
    prs_df = pd.read_csv(prs_path)
    review_comments_df = pd.read_csv(review_comments_path)
    print(f"[INFO] Commits loaded: {len(commits_df)}, PRs loaded: {len(prs_df)}, Comments loaded: {len(review_comments_df)}")

    for col in ["created_at", "merged_at"]:
        if col in prs_df.columns:
            print(f"[INFO] Converting '{col}' in PRs to UTC Z format (if needed)...")
            prs_df[col] = prs_df[col].apply(
                lambda x: pd.to_datetime(x, errors='coerce', utc=True).strftime('%Y-%m-%dT%H:%M:%SZ')
                if pd.notna(x) and not str(x).endswith("Z") else x
            )

    if "created_at" in review_comments_df.columns:
        print("[INFO] Converting 'created_at' in review comments to UTC Z format (if needed)...")
        review_comments_df["created_at"] = review_comments_df["created_at"].apply(
            lambda x: pd.to_datetime(x, errors='coerce', utc=True).strftime('%Y-%m-%dT%H:%M:%SZ')
            if pd.notna(x) and not str(x).endswith("Z") else x
        )

    for name, df in [("commits", commits_df), ("prs", prs_df), ("comments", review_comments_df)]:
        if "pr_id" not in df.columns:
            raise KeyError(f"[ERROR] '{name}' file is missing required column 'pr_id'.")

    valid_pr_ids = set(commits_df["pr_id"].dropna().unique())
    prs_before, review_before = len(prs_df), len(review_comments_df)
    prs_df = prs_df[prs_df["pr_id"].isin(valid_pr_ids)]
    review_comments_df = review_comments_df[review_comments_df["pr_id"].isin(valid_pr_ids)]
    print(f"[INFO] Filtered PRs: {prs_before} → {len(prs_df)}")
    print(f"[INFO] Filtered review comments: {review_before} → {len(review_comments_df)}")

    def get_top_file_info(group):
        file_sums = group.groupby("file_path")[["lines_added", "lines_deleted"]].sum()
        file_sums["total_change"] = file_sums["lines_added"] + file_sums["lines_deleted"]
        if file_sums.empty:
            return pd.Series({"top_file": None, "top_file_change_%": None, "docs_updated": False})

        top_file_row = file_sums.sort_values("total_change", ascending=False).iloc[0]
        top_file = top_file_row.name
        top_file_total_change = top_file_row["total_change"]
        total_pr_change = file_sums["total_change"].sum()
        top_file_change_pct = round((top_file_total_change / total_pr_change) * 100, 2) if total_pr_change > 0 else None
        docs_updated = any("docs" in str(fp).lower() or "readme" in str(fp).lower() for fp in file_sums.index)
        return pd.Series({"top_file": top_file, "top_file_change_%": top_file_change_pct, "docs_updated": docs_updated})

    print("[INFO] Calculating top file metrics per PR...")
    top_file_info = commits_df.groupby("pr_id", group_keys=False).apply(get_top_file_info).reset_index()
    enriched_prs = prs_df.merge(top_file_info, on="pr_id", how="left")

    print("[INFO] Calculating order_of_review for review comments...")
    if not review_comments_df.empty:
        if "created_at" not in review_comments_df.columns:
            raise KeyError("[ERROR] review-comments.csv is missing 'created_at' column.")
        review_comments_df["created_at"] = pd.to_datetime(review_comments_df["created_at"], errors="coerce")
        review_comments_df = review_comments_df.sort_values(["pr_id", "created_at"])
        review_comments_df["order_of_review"] = (
            review_comments_df.groupby("pr_id")["created_at"]
            .rank(method="first")
            .astype(int)
            .apply(lambda x: "first" if x == 1 else ("second" if x == 2 else "additional"))
        )

    enriched_prs.to_csv(prs_path, index=False)
    review_comments_df.to_csv(review_comments_path, index=False)

    print(f"[SUCCESS] Updated PRs saved to: {prs_path}")
    print(f"[SUCCESS] Updated review comments saved to: {review_comments_path}")
    print(f"[INFO] Final PR count: {len(enriched_prs)} | Final comments count: {len(review_comments_df)}")

# === BRANCH NAME CLEANING =============================================
def clean_and_impute_branch_names(input_path, output_path):
    """
    Reads a CSV, imputes missing branch_name values based on the same pr_id,
    and saves the cleaned data to a new CSV.
    """
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir)

    if not os.path.exists(input_path):
        print(f"Error: Input file not found at {input_path}. Skipping.")
        return

    print(f"Loading data from {input_path}...")
    
    try:
        df = pd.read_csv(input_path)
    except pd.errors.EmptyDataError:
        print(f"Warning: File {input_path} is empty. Skipping.")
        return
    except Exception as e:
        print(f"An error occurred reading {input_path}: {e}")
        return

    if 'pr_id' not in df.columns:
        print("Error: 'pr_id' column not found. Cannot proceed with imputation.")
        return
    if 'branch_name' not in df.columns:
        print("Error: 'branch_name' column not found. Cannot proceed with imputation.")
        return

    try:
        df['pr_id'] = pd.to_numeric(df['pr_id'], errors='coerce').astype(pd.Int64Dtype())
    except Exception as e:
        print(f"Warning: Could not convert 'pr_id' to integer. Proceeding with original type. Error: {e}")
        
    df['branch_name'] = df['branch_name'].replace('', np.nan)
    initial_missing = df['branch_name'].isna().sum()

    print(f"Found {initial_missing} records with missing branch_name initially.")

    valid_branches = df.dropna(subset=['branch_name', 'pr_id'])
    branch_map = valid_branches.drop_duplicates(subset=['pr_id'], keep='first').set_index('pr_id')['branch_name']
    df['branch_name'].fillna(df['pr_id'].map(branch_map), inplace=True)

    filled_count = initial_missing - df['branch_name'].isna().sum()

    try:
        df.to_csv(output_path, index=False)
        print("-" * 50)
        print(f"Cleaning complete for {input_path}.")
        print(f"-> Successfully imputed {filled_count} missing branch names based on matching pr_id.")
        print(f"-> The cleaned data is saved to: {output_path}")
    except Exception as e:
        print(f"An error occurred writing to {output_path}: {e}")

# === TIMESTAMP FIX FUNCTION ===========================================
def adjust_merge_timestamps(combined_df):
    """Fix chronological ordering by making merge events occur after the last commit."""
    print("  Adjusting merge event timestamps for chronological ordering...")
    
    combined_df["created_at"] = pd.to_datetime(combined_df["created_at"], utc=True, errors="coerce")
    
    merge_mask = (combined_df["main_label"] == "Merge State")
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
    for idx in combined_df[merge_mask].index:
        row = combined_df.loc[idx]
        pr_id = row["pr_id"]
        
        merged_at = row.get("merged_at")
        if pd.notna(merged_at):
            combined_df.at[idx, "created_at"] = pd.to_datetime(merged_at, utc=True)
            adjusted_count += 1
        elif pr_id in pr_last_commit_times:
            new_timestamp = pr_last_commit_times[pr_id] + pd.Timedelta(seconds=1)
            combined_df.at[idx, "created_at"] = new_timestamp
            adjusted_count += 1
    
    print(f"    Adjusted {adjusted_count} merge event timestamps")
    return combined_df

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

def get_branch_pr_mapping(prs_df):
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
    mapping_path = "../../confidential/anonymized_usernames.json"
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

# === OLLAMA HELPER ====================================================
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
            print(f"Ollama error: {err} — retrying in 3 seconds...")
            time.sleep(3)

# === BRANCHING LABELING FUNCTIONS ======================================
def label_features_per_branch(prs_df):
    """Label: one, multiple - Counts how many features (PRs) were created per branch."""
    result_rows = []
    
    branch_mapping = get_branch_pr_mapping(prs_df)
    
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
    """Label: meaningful, random - Uses LLM to determine if branch names are descriptive."""
    print("  Evaluating branch naming via Ollama...")
    result_rows = []
    llm_reasoning_rows = []

    branch_mapping = get_branch_pr_mapping(prs_df)
    unique_branches = get_unique_branch_names(prs_df)
    
    if not unique_branches:
        print("    No branch names found to evaluate")
        return pd.DataFrame(), pd.DataFrame()

    branch_context = {}
    for branch_name, pr_list in branch_mapping.items():
        if pr_list:
            first_pr = pr_list[0]
            pr_id = first_pr["pr_id"]
            pr_row = prs_df[prs_df["pr_id"] == pr_id]
            if not pr_row.empty:
                pr_row = pr_row.iloc[0]
                branch_context[branch_name] = {
                    "pr_title": str(pr_row.get("pr_title", "")),
                    "pr_description": str(pr_row.get("pr_description", ""))
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

        pr_title = ""
        pr_description = ""
        if branch_name in branch_context:
            pr_title = branch_context[branch_name]["pr_title"]
            pr_description = branch_context[branch_name]["pr_description"]

        name_label, llm_raw = assess_branch_meaningfulness(
            branch_name, pr_title, pr_description
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
                    "pr_title": pr_title,
                    "pr_description": pr_description,
                    "branch_naming_label": name_label,
                    "llm_reasoning": llm_raw,
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

# === MERGE STATE LABELING =============================================
def label_merge_state(prs_df):
    """Label: no_merge, self_merge, reviewed_merge - Determines how the PR was merged."""
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        merged_at = row.get("merged_at")
        created_at = row.get("created_at")
        
        merged_by_from_row = row.get("merged_by")
        
        if pd.isna(merged_at) or merged_at == '' or merged_at is None:
            event = "no_merge"
            llm_output = "rule-based: PR not merged"
        else:
            merged_by = str(merged_by_from_row).strip()
            pr_author_str = str(pr_author).strip()
            
            if merged_by and pr_author_str and merged_by.lower() == pr_author_str.lower(): 
                event = "self_merge"
                llm_output = f"rule-based: self-merged by {pr_author}"
            else:
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
    base_path = Path("../../data/csv/")
    
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
        print(f"Processing {team_name}...")
        print('='*60)

        prs_path = None
        for pattern in [
            f"{team_name}_all_pull_requests_fixed.csv",
            f"{team_name}_all_pull_requests.csv",
            f"{team_name}_PRs.csv",
            f"{team_name}_pull_requests.csv",
            "all_pull_requests.csv"
        ]:
            potential_path = team_folder / pattern
            if potential_path.exists():
                prs_path = potential_path
                break

        if not prs_path:
            print(f"Missing PRs CSV for {team_name}, skipping.")
            continue

        commits_path = None
        for pattern in [
            f"{team_name}_commit_file_changes.csv",
            f"{team_name}_PR_commits_fixed.csv",
            f"{team_name}_commits.csv",
            "PR_commits.csv"
        ]:
            potential_path = team_folder / pattern
            if potential_path.exists():
                commits_path = potential_path
                print(f"Found commits file: {potential_path.name}")
                if "file_changes" in pattern:
                    print(f"   Using file-level commit data (best for granular analysis)")
                else:
                    print(f"   Using commit-level data (limited file-level detail)")
                break

        print(f"Loading PRs from: {prs_path.name}")
        prs_df = pd.read_csv(prs_path)
        
        # Filter out bot PRs using utility function
        prs_df = remove_bot_prs(prs_df, verbose=True)
        
        if "created_at" in prs_df.columns:
            prs_df["created_at"] = prs_df["created_at"].apply(normalize_timestamp_to_utc_z)
        if "merged_at" in prs_df.columns:
            prs_df["merged_at"] = prs_df["merged_at"].apply(normalize_timestamp_to_utc_z)
            
        prs_df["created_at"] = pd.to_datetime(prs_df["created_at"], utc=True, errors="coerce")
        prs_df["merged_at"] = pd.to_datetime(prs_df["merged_at"], utc=True, errors="coerce")

        original_pr_count = len(prs_df)
        prs_df = prs_df.dropna(subset=["created_at"])
        if len(prs_df) < original_pr_count:
             print(f"[WARN] Dropped {original_pr_count - len(prs_df)} PRs due to missing/invalid 'created_at' timestamp.")

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

        unique_branches = get_unique_branch_names(prs_df)
        branch_mapping = get_branch_pr_mapping(prs_df)
        print(f"[INFO] Processing {len(unique_branches)} unique branch names across {len(prs_df)} PRs")

        if ANONYMIZE:
            if name_map:
                print(f"Anonymizing PR authors...")
                prs_df["pr_author"] = anonymize_column(prs_df["pr_author"], name_map)
                
                if "head_branch" in prs_df.columns:
                    print(f"Anonymizing branch names...")
                    prs_df["head_branch"] = anonymize_branch_names(prs_df["head_branch"], name_map)
            else:
                print(f"Anonymization enabled but no mapping loaded - skipping anonymization")

        commits_df = None
        if commits_path:
            print(f"Loading commits from: {commits_path.name}")
            commits_df = pd.read_csv(commits_path)
            
            # Filter out bot commits using utility function
            commits_df = remove_bot_commits(commits_df, verbose=True)
            
            commits_df["commit_date"] = pd.to_datetime(commits_df.get("commit_date"), errors="coerce")

            if ANONYMIZE and "author" in commits_df.columns and name_map:
                print(f"Anonymizing commit authors...")
                commits_df["author"] = anonymize_column(commits_df["author"], name_map)
        else:
            print(f"Warning: No commits CSV found for {team_name}")

        all_labels = []
        llm_reasoning_data = []

        print("\nGenerating Code Structure / Branching Labels...")
        
        print("  - Features per branch (one, multiple)...")
        try:
            features_per_branch_labels = label_features_per_branch(prs_df.copy())
            if not features_per_branch_labels.empty:
                all_labels.append(features_per_branch_labels)
                print(f"    Generated {len(features_per_branch_labels)} events")
        except Exception as e:
            print(f"    Error: {e}")

        print("  - Branch names (meaningful, random)...")
        try:
            branch_name_labels, branch_name_reasoning = label_branch_names(prs_df.copy())
            if not branch_name_labels.empty:
                all_labels.append(branch_name_labels)
                print(f"    Generated {len(branch_name_labels)} events")
            if not branch_name_reasoning.empty:
                llm_reasoning_data.append(branch_name_reasoning)
        except Exception as e:
            print(f"    Error: {e}")

        if commits_df is not None:
            print("  - Feature size (small, large)...")
            try:
                feature_size_labels = label_feature_size(commits_df.copy(), prs_df.copy(), pr_created_at_lookup)
                if not feature_size_labels.empty:
                    all_labels.append(feature_size_labels)
                    print(f"    Generated {len(feature_size_labels)} events")
            except Exception as e:
                print(f"    Error: {e}")

            print("  - Refactor size (small, large)...")
            try:
                refactor_size_labels = label_refactor_size(commits_df.copy(), prs_df.copy(), pr_created_at_lookup)
                if not refactor_size_labels.empty:
                    all_labels.append(refactor_size_labels)
                    print(f"    Generated {len(refactor_size_labels)} events")
            except Exception as e:
                print(f"    Error: {e}")

        print("  - Repository status (up-to-date, outdated)...")
        try:
            repo_status_labels = label_repo_status(prs_df.copy())
            if not repo_status_labels.empty:
                all_labels.append(repo_status_labels)
                print(f"    Generated {len(repo_status_labels)} events")
        except Exception as e:
            print(f"    Error: {e}")

        print("  - PR status (closed, still_open)...")
        try:
            pr_status_labels = label_pr_status(prs_df.copy())
            if not pr_status_labels.empty:
                all_labels.append(pr_status_labels)
                print(f"    Generated {len(pr_status_labels)} events")
        except Exception as e:
            print(f"    Error: {e}")

        print("  - Merge state (no_merge, self-merge, reviewed_merge)...")
        try:
            merge_state_labels = label_merge_state(prs_df.copy())
            if not merge_state_labels.empty:
                all_labels.append(merge_state_labels)
                print(f"    Generated {len(merge_state_labels)} events")
        except Exception as e:
            print(f"    Error: {e}")

        if not all_labels:
            print(f"No labels generated for {team_name}, continuing to next team.")
            continue

        combined = pd.concat(all_labels, ignore_index=True, sort=False)
        combined["created_at"] = pd.to_datetime(combined["created_at"], utc=True, errors="coerce")

        combined = adjust_merge_timestamps(combined)
        
        diagnose_timestamp_issues(combined)
        
        if "created_at" in combined.columns:
            combined["created_at"] = combined["created_at"].apply(
                lambda x: x.strftime('%Y-%m-%dT%H:%M:%SZ') if pd.notna(x) else ''
            )

        suffix = "_anonymized" if ANONYMIZE and name_map else ""
        
        out_path = base_path / f"code_structure_branching_labels_{team_name}{suffix}.csv"
        
        try:
            combined.to_csv(out_path, index=False)
            print(f"\nSaved combined event labels to: {out_path}")
            
            if ANONYMIZE and name_map:
                print(f"Anonymized authors in output:")
                unique_authors = combined["pr_author"].unique()
                for author in sorted(unique_authors):
                    count = (combined["pr_author"] == author).sum()
                    print(f"   {author}: {count} events")
        except Exception as e:
            print(f"Failed to save labels to {out_path}: {e}")
        
        if llm_reasoning_data:
            graphs_folder = team_folder / "graphs"
            reasoning_folder = graphs_folder / "reasoning"
            reasoning_folder.mkdir(parents=True, exist_ok=True)
            
            combined_llm = pd.concat(llm_reasoning_data, ignore_index=True, sort=False)
            combined_llm["created_at"] = pd.to_datetime(combined_llm["created_at"], utc=True, errors="coerce")
            
            if "created_at" in combined_llm.columns:
                combined_llm["created_at"] = combined_llm["created_at"].apply(
                    lambda x: x.strftime('%Y-%m-%dT%H:%M:%SZ') if pd.notna(x) else ''
                )
            
            llm_out_path = reasoning_folder / f"{team_name}_all_llm_reasoning{suffix}.csv"
            
            try:
                combined_llm.to_csv(llm_out_path, index=False)
                print(f"Saved LLM reasoning data to: {llm_out_path}")
            except Exception as e:
                print(f"Failed to save LLM reasoning to {llm_out_path}: {e}")
        
        # Clean branch names after labeling
        print("\nCleaning branch names...")
        clean_folder = base_path / "clean"
        clean_folder.mkdir(exist_ok=True)
        clean_output_path = clean_folder / f"code_structure_branching_labels_{team_name}{suffix}.csv"
        clean_and_impute_branch_names(str(out_path), str(clean_output_path))

    print("\n" + "="*60)
    print("ALL TEAMS PROCESSED")
    print("="*60)
    if ANONYMIZE and name_map:
        print("Anonymization was ENABLED for all outputs")
    elif ANONYMIZE and not name_map:
        print("Anonymization was ENABLED but no mapping was loaded")
    else:
        print("Anonymization was DISABLED")
    print("="*60)

# === MAIN EXECUTION ===================================================
if __name__ == "__main__":
    process_all_teams()