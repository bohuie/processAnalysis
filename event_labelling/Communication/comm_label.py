import os
import glob
import re
import pandas as pd
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
from datetime import datetime

from src.utils.connect_groq import connect_groq              # LLM client (Groq)
from src.utils.ollama_offline import connect_ollama_offline  # LLM client (Offline Ollama)
from src.utils.normalize_pr_id import normalize_pr_ids       # PR ID normalization
from src.utils.anonymize_columns import (
    anonymize_author_columns,
    anonymize_column,
)  # final author anonymization
from src.utils.label_merge import label_merge_state          # merge-state labels
from src.utils.botFilter import filter_bots_from_multiple_columns  # 🔹 NEW: bot filter


# === HELPERS =========================================================
def append_event(event_list, new_event):
    """Safely append a new label to the event list (avoiding duplicates)."""
    if not isinstance(event_list, list):
        event_list = []
    if new_event and new_event not in event_list:
        event_list.append(new_event)
    return event_list


def find_file(folder, patterns):
    """Return the first existing path matching any pattern in a folder."""
    for pattern in patterns:
        potential_path = os.path.join(folder, pattern)
        if os.path.exists(potential_path):
            return potential_path
    return None


# === SETUP ============================================================
load_dotenv()

RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data", "csve")
os.makedirs(DATA_FOLDER, exist_ok=True)
CACHE_PATH = os.path.join(DATA_FOLDER, "commit_message_cache.csv")

PR_LOOKUP_PATH = os.path.join(DATA_FOLDER, "pr_timestamp_lookup.csv")
REVIEW_LOOKUP_PATH = os.path.join(DATA_FOLDER, "review_timestamp_lookup.csv")

# === FIND ALL TEAM FOLDERS ============================================
team_folders = glob.glob(os.path.join(DATA_FOLDER, "year-long-project-team-*"))
if not team_folders:
    raise FileNotFoundError(f"❌ No team folders found in {DATA_FOLDER}")

print(f"[INFO] Found {len(team_folders)} team folders:")
for t in team_folders:
    print(" -", os.path.basename(t))

# === LLM ALIAS (Check AI_MODE toggle) ================================
AI_MODE = os.getenv("AI_MODE", "online").lower()
if AI_MODE == "offline":
    ask_llm = connect_ollama_offline
    print(f"[INFO] AI_MODE=offline, using local Ollama")
else:
    ask_llm = connect_groq
    print(f"[INFO] AI_MODE=online, using Groq API")


# === LLM-BASED CLASSIFIERS ============================================
def classify_commit_message(msg, cache):
    msg = str(msg).strip()
    if msg == "" or msg.lower() == "nan":
        return "commit_uninformative", ""
    if msg in cache:
        event_label = cache[msg]
        llm_output = "informative" if event_label == "commit_informative" else "uninformative"
        return event_label, llm_output

    prompt = f"""
    Determine if the following commit message contains both a verb and a noun.
    If it does, respond ONLY with 'informative'. If not, respond ONLY with 'uninformative'.
    Commit message: \"\"\"{msg}\"\"\"
    """
    llm_output = ask_llm(prompt, max_tokens=20)
    resp = llm_output.lower()
    label = "commit_informative" if "informative" in resp and "un" not in resp else "commit_uninformative"
    cache[msg] = label
    return label, llm_output


def classify_constructiveness(comment_text):
    prompt = f"""
    You are analyzing a GitHub review comment.
    Classify the comment as either 'constructive' or 'non_constructive'.
    Use these criteria:

    CONSTRUCTIVE IF the comment:
    - Addresses functional defects
    - Points out validation issues or alternative use cases
    - Suggests changes to APIs, resources, or conventions
    - Mentions style/naming/indentation/typos
    - Requests refactoring or simplification

    NON-CONSTRUCTIVE IF the comment:
    - States opinions as fact (e.g., "This should be stateless")
    - Is sarcastic/judgmental ("Did you even test this?")
    - Piggybacks on a previous comment without adding insight

    Classify the comment below and briefly explain reasoning (1 short sentence per comment).
    Comment: \"\"\"{comment_text}\"\"\"
    Respond format: label | reasoning
    """
    return ask_llm(prompt, max_tokens=150)


def label_pr_descriptions(prs_df):
    desc_col = "pr_description" if "pr_description" in prs_df.columns else "body"
    labels = []
    for _, pr in prs_df.iterrows():
        description = str(pr.get(desc_col, "")).strip()
        word_count = len(description.split())
        if word_count >= 10:
            event = "pr_description_clear"
        else:
            event = "pr_description_unclear"
        labels.append({
            "pr_id": pr.get("pr_id", np.nan),
            "pr_author": pr.get("pr_author", "unknown"),
            "created_at": pr.get("created_at", pd.NaT),
            "event": event,
            "main_label": "PR"
        })
    return pd.DataFrame(labels)


# Utility to drop bot rows from any *author*-like and merged_by columns
def drop_bots_in_author_like_columns(df: pd.DataFrame, df_label: str) -> pd.DataFrame:
    author_cols = [c for c in df.columns if "author" in c.lower()]
    bot_cols = list(author_cols)
    if "merged_by" in df.columns:
        bot_cols.append("merged_by")

    if not bot_cols:
        print(f"[INFO] No author/merged_by columns found in {df_label}, skipping bot filter.")
        return df

    print(f"[STEP -1] Filtering bots in {df_label} using columns: {bot_cols}")
    return filter_bots_from_multiple_columns(
        df,
        username_columns=bot_cols,
        filter_mode="any",   # drop row if ANY of these columns is a bot
        inplace=False,
        verbose=True,
    )
    

LOG_PATTERN = re.compile(r"\blog(s?)\b", re.IGNORECASE)


def drop_log_rows(df: pd.DataFrame, df_label: str) -> pd.DataFrame:
    """
    Remove rows where ANY cell contains the word 'log' or 'logs' (case-insensitive).
    Uses regex: \\blog(s?)\\b
    """
    if df.empty:
        print(f"[INFO] {df_label}: DataFrame empty, skipping log filter.")
        return df

    # Convert all cells to string for safe matching
    str_df = df.astype(str)

    # For each column, check if it contains 'log' / 'logs', then OR across columns
    col_matches = str_df.apply(
        lambda col: col.str.contains(LOG_PATTERN, na=False),
        axis=0
    )
    row_has_log = col_matches.any(axis=1)

    before = len(df)
    filtered_df = df[~row_has_log].copy()
    removed = before - len(filtered_df)

    print(f"[STEP -1B] {df_label}: removed {removed} rows containing 'log'/'logs' "
          f"({before} -> {len(filtered_df)}).")
    return filtered_df



# === MAIN LOOP: EACH TEAM ============================================
for TEAM_FOLDER in team_folders:
    team_name = os.path.basename(TEAM_FOLDER)
    print(f"\n{'='*70}")
    print(f"Processing {team_name} ...")
    print('='*70)

    # === Flexible naming patterns =====================================
    prs_patterns = [
        f"{team_name}_all_pull_requests.csv",
        f"{team_name}_PRs.csv",
        "all_pull_requests.csv"
    ]

    commits_patterns = [
        f"{team_name}_PR_commits.csv",
        f"{team_name}_commits.csv",
        "PR_commits.csv"
    ]

    reviews_patterns = [
        f"{team_name}_review-comments.csv",
        "review-comments.csv"
    ]

    # === Locate files =================================================
    PRS_PATH = find_file(TEAM_FOLDER, prs_patterns)
    COMMITS_PATH = find_file(TEAM_FOLDER, commits_patterns)
    REVIEWS_PATH = find_file(TEAM_FOLDER, reviews_patterns)

    # === Output path ==================================================
    OUTPUT_PATH = os.path.join(DATA_FOLDER, f"pr_communications_labels_{team_name}.csv")

    # === Validate file existence =====================================
    missing = []
    if not PRS_PATH:
        missing.append("PRs file")
    if not COMMITS_PATH:
        missing.append("Commits file")
    if not REVIEWS_PATH:
        missing.append("Review-comments file")

    if missing:
        print(f"❌ Missing files for {team_name}: {', '.join(missing)}")
        print("Skipping this team.\n")
        continue

    print(f"[OK] Found all CSVs for {team_name}")
    print(f"[INFO] Output will be saved as: {OUTPUT_PATH}")

    # === STEP -1A: FILTER BOTS IN RAW CSVs ============================
    print("[STEP -1A] Removing bot usernames from author/merged_by columns...")

    raw_prs_df = pd.read_csv(PRS_PATH)
    raw_commits_df = pd.read_csv(COMMITS_PATH)
    raw_reviews_df = pd.read_csv(REVIEWS_PATH)

    # 1) Remove bots
    raw_prs_df = drop_bots_in_author_like_columns(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_bots_in_author_like_columns(raw_commits_df, f"{team_name} Commits")
    raw_reviews_df = drop_bots_in_author_like_columns(raw_reviews_df, f"{team_name} Reviews")

    # 2) Remove rows mentioning logs/log
    raw_prs_df = drop_log_rows(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_log_rows(raw_commits_df, f"{team_name} Commits")
    raw_reviews_df = drop_log_rows(raw_reviews_df, f"{team_name} Reviews")

    # Overwrite the CSVs with cleaned data
    raw_prs_df.to_csv(PRS_PATH, index=False)
    raw_commits_df.to_csv(COMMITS_PATH, index=False)
    raw_reviews_df.to_csv(REVIEWS_PATH, index=False)


    # === STEP -1B: ANONYMIZE AUTHOR COLUMNS (on disk) =================
    csv_paths = {
        "prs": PRS_PATH,
        "commits": COMMITS_PATH,
        "reviews": REVIEWS_PATH,
    }
    anonymize_author_columns(csv_paths)

    # === LOAD CACHE ===================================================
    if os.path.exists(CACHE_PATH):
        cache_df = pd.read_csv(CACHE_PATH)
        cache = dict(zip(cache_df["commit_message"], cache_df["event"]))
        print(f"[INFO] Loaded {len(cache)} cached commit analyses.")
    else:
        cache = {}

    # === LOAD CSVs (already bot-filtered + anonymized) ================
    print("[INFO] Loading CSVs with parsed timestamps...")
    prs_df = pd.read_csv(PRS_PATH, parse_dates=["created_at"])
    commits_df = pd.read_csv(COMMITS_PATH)
    reviews_df = pd.read_csv(REVIEWS_PATH, parse_dates=["created_at"])
    print(f"[OK] PRs: {len(prs_df)} | Commits: {len(commits_df)} | Reviews: {len(reviews_df)}")

    # === Normalize PR IDs via utility =================================
    dfs = {"prs_df": prs_df, "commits_df": commits_df, "reviews_df": reviews_df}
    dfs = normalize_pr_ids(dfs)
    prs_df, commits_df, reviews_df = dfs["prs_df"], dfs["commits_df"], dfs["reviews_df"]

    # === STEP 0: LOOKUPS ==============================================
    print("[STEP 0] Building timestamp lookups...")
    pr_lookup = prs_df[["pr_id", "created_at"]].dropna(subset=["pr_id", "created_at"]).drop_duplicates(subset=["pr_id"])
    pr_time_lookup = pr_lookup.set_index("pr_id")["created_at"].to_dict()
    pr_lookup.to_csv(PR_LOOKUP_PATH, index=False)

    if "comment_id" in reviews_df.columns:
        review_lookup = reviews_df[["comment_id", "created_at"]].dropna(subset=["comment_id", "created_at"]).drop_duplicates(subset=["comment_id"])
        review_time_lookup = review_lookup.set_index("comment_id")["created_at"].to_dict()
        review_lookup.to_csv(REVIEW_LOOKUP_PATH, index=False)
    else:
        review_time_lookup = {}

    # === STEP 1: COMMIT INFORMATIVENESS ===============================
    print("[STEP 1] Evaluating commit informativeness with Groq (cached)...")
    commits_df["event"] = [[] for _ in range(len(commits_df))]
    commits_df["llm_output"] = ""
    commits_df["llm_timestamp"] = ""

    for i, msg in enumerate(tqdm(commits_df["commit_message"].fillna(""))):
        label, llm_raw = classify_commit_message(msg, cache)
        commits_df.at[i, "event"] = append_event(commits_df.at[i, "event"], label)
        commits_df.at[i, "llm_output"] = llm_raw
        commits_df.at[i, "llm_timestamp"] = RUN_TIMESTAMP if llm_raw else ""

    commits_df["main_label"] = "Communication"
    commits_df["created_at"] = commits_df["pr_id"].map(pr_time_lookup)

    # === STEP 2: PR LABELS ===========================================
    print("[STEP 2] Labelling PRs (docs + merge state)...")

    prs_df["event"] = [[] for _ in range(len(prs_df))]

    # 2a) Documentation labels (feature_documented / feature_undocumented)
    for i, row in prs_df.iterrows():
        docs_flag = bool(row.get("docs_updated", False))
        doc_label = "feature_documented" if docs_flag else "feature_undocumented"
        prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], doc_label)

    # 2b) Merge-state labels via utility
    merge_labels_df = label_merge_state(prs_df)
    merge_event_map = merge_labels_df.set_index("pr_id")["event"].to_dict()

    for i, row in prs_df.iterrows():
        pr_id = row.get("pr_id")
        merge_event = merge_event_map.get(pr_id)
        if merge_event:
            prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], merge_event)

    prs_df["llm_output"] = ""
    prs_df["llm_timestamp"] = ""
    prs_df["main_label"] = "Communication"
    prs_df["pr_author"] = prs_df.get("pr_author", "unknown")

    # === STEP 3: REVIEWS ==============================================
    print("[STEP 3] Evaluating review attributes and constructiveness...")

    review_counts = reviews_df.groupby("pr_id").size().reset_index(name="comment_count")
    reviews_df = reviews_df.merge(review_counts, on="pr_id", how="left")

    reviews_df["comment_body"] = reviews_df["comment_body"].fillna("")
    reviews_df["state_lower"] = reviews_df["state"].fillna("").str.lower()
    reviews_df["is_empty_comment"] = reviews_df["comment_body"].astype(str).str.strip().eq("")
    reviews_df["is_empty_approved"] = reviews_df["is_empty_comment"] & reviews_df["state_lower"].eq("approved")

    reviews_df["event"] = [[] for _ in range(len(reviews_df))]
    reviews_df["llm_output"] = ""
    reviews_df["llm_timestamp"] = ""
    reviews_df["main_label"] = "Communication"
    reviews_df["pr_author"] = reviews_df.get("user_login", "unknown")

    reviews_df["created_at"] = reviews_df["created_at"].combine_first(
        reviews_df["comment_id"].map(review_time_lookup) if "comment_id" in reviews_df.columns else pd.Series([pd.NaT] * len(reviews_df))
    )
    reviews_df["created_at"] = reviews_df["created_at"].combine_first(reviews_df["pr_id"].map(pr_time_lookup))

    for i, row in tqdm(reviews_df.iterrows(), total=len(reviews_df)):
        state = row.get("state_lower", "")
        is_empty_comment = bool(row.get("is_empty_comment", False))
        is_empty_approved = bool(row.get("is_empty_approved", False))

        if state == "changes_requested":
            reviews_df.at[i, "event"] = append_event(reviews_df.at[i, "event"], "changes_requested")
        elif is_empty_approved:
            reviews_df.at[i, "event"] = append_event(reviews_df.at[i, "event"], "empty_review_comment")

        if not is_empty_comment:
            comment = str(row.get("comment_body", "")).strip()
            if comment:
                llm_response = classify_constructiveness(comment)
                resp_lower = llm_response.lower()
                label = "constructive" if "constructive" in resp_lower and "non" not in resp_lower else "non_constructive"
                reason = llm_response.split("|")[-1].strip() if "|" in llm_response else llm_response
                order = str(row.get("order_of_review", "first")).lower()

                if "1" in order or "first" in order:
                    event = f"{label}_first_review"
                elif "2" in order or "second" in order:
                    event = f"{label}_second_review"
                else:
                    event = f"{label}_additional_review"

                reviews_df.at[i, "event"] = append_event(reviews_df.at[i, "event"], event)
                reviews_df.at[i, "llm_output"] = reason
                reviews_df.at[i, "llm_timestamp"] = RUN_TIMESTAMP

    # === STEP 4: PR DESCRIPTION =======================================
    desc_labels = label_pr_descriptions(prs_df)

    commits_df["source"] = "commit"
    prs_df["source"] = "pr"
    reviews_df["source"] = "review"

    # === STEP 6: COMBINE + FINAL CLEANUP ==============================
    print("[STEP 6] Combining and final cleanup...")

    combined = pd.concat([commits_df, prs_df, reviews_df, desc_labels], ignore_index=True)
    combined["created_at"] = pd.to_datetime(combined["created_at"], errors="coerce")
    combined["created_at"].fillna(method="ffill", inplace=True)
    combined["pr_author"].replace("", np.nan, inplace=True)
    combined["pr_author"].fillna("unknown", inplace=True)
    combined["event"] = combined["event"].apply(lambda x: str(x) if isinstance(x, list) else x)
    combined = combined.sort_values("created_at").reset_index(drop=True)

    if "author" in combined.columns and "pr_author" in combined.columns:
        combined["author"] = combined["author"].fillna(combined["pr_author"])
        combined = combined.dropna(subset=["author"])
        combined = combined.drop(columns=["pr_author"], errors="ignore")
        combined = combined.rename(columns={"author": "pr_author"})

    # === STEP 7: SPLIT OUTPUTS (PR vs Communication) ==================
    PR_LABELS = {
        "self_merge", "reviewed_merge", "no_merge",
        "constructive_first_review", "constructive_second_review", "constructive_additional_review",
        "non_constructive_first_review", "non_constructive_second_review", "non_constructive_additional_review",
        "pr_description_clear", "pr_description_unclear", "changes_requested", "empty_review_comment"
    }

    COMM_LABELS = {
        "feature_documented", "feature_undocumented",
        "commit_informative", "commit_uninformative",
        "self_merge", "no_merge", "reviewed_merge"
    }

    print("[STEP 7] Splitting combined dataset into PR and Communication subsets...")

    def safe_parse(x):
        if isinstance(x, str):
            try:
                val = eval(x)
                if isinstance(val, list):
                    return val
                return [val]
            except Exception:
                return [x]
        elif isinstance(x, list):
            return x
        else:
            return [x]

    combined["event_list"] = combined["event"].apply(safe_parse)

    pr_rows, comm_rows = [], []
    for _, row in combined.iterrows():
        evs = [e for e in row["event_list"] if isinstance(e, str)]
        pr_evs = [e for e in evs if e in PR_LABELS]
        comm_evs = [e for e in evs if e in COMM_LABELS]
        if pr_evs:
            new_row = row.copy()
            new_row["event"] = str(pr_evs)
            new_row["event_list"] = pr_evs
            pr_rows.append(new_row)
        if comm_evs:
            new_row = row.copy()
            new_row["event"] = str(comm_evs)
            new_row["event_list"] = comm_evs
            comm_rows.append(new_row)

    pr_df = pd.DataFrame(pr_rows)
    comm_df = pd.DataFrame(comm_rows)

    # === SAVE BOTH FILES =============================================
    PR_OUTPUT_PATH = os.path.join(DATA_FOLDER, f"pr_labels_{team_name}.csv")
    COMM_OUTPUT_PATH = os.path.join(DATA_FOLDER, f"communication_labels_{team_name}.csv")

    if not pr_df.empty:
        pr_df.to_csv(PR_OUTPUT_PATH, index=False)
        print(f"[OK] PR labels saved → {PR_OUTPUT_PATH} ({len(pr_df)} rows)")
    else:
        print("[WARN] No PR labels found to save.")

    if not comm_df.empty:
        comm_df.to_csv(COMM_OUTPUT_PATH, index=False)
        print(f"[OK] Communication labels saved → {COMM_OUTPUT_PATH} ({len(comm_df)} rows)")
    else:
        print("[WARN] No Communication labels found to save.")

    print(f"[INFO] Combined source: {len(combined)} rows → PR={len(pr_df)} + Comm={len(comm_df)} (including shared rows).")
