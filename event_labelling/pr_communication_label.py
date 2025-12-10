import os
import glob
import time
import pandas as pd
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv
# from groq import Groq  # REMOVED: Groq library
import requests  # NEW: for Ollama API calls
import json       # NEW: for response handling
from datetime import datetime

# === HELPER ==========================================================
def append_event(event_list, new_event):
    """Safely append a new label to the event list (avoiding duplicates)."""
    if not isinstance(event_list, list):
        event_list = []
    if new_event and new_event not in event_list:
        event_list.append(new_event)
    return event_list


# === SETUP ============================================================
load_dotenv()
# --- OLLAMA CONFIG ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3.2:3b")  # e.g., llama3:8b, mistral, etc.
MODEL_NAME = OLLAMA_MODEL_NAME
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


# === LLM CALLER FOR OLLAMA ============================================
def ask_ollama(prompt, max_tokens=200):
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a precise text classifier and explainer."},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.2,
            "num_predict": max_tokens
        },
        "stream": False
    }

    while True:
        try:
            response = requests.post(url, json=payload, timeout=600)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                print("⚠️ Rate-limit hit — sleeping 5s...")
                time.sleep(5)
                continue
            print(f"⚠️ Ollama HTTP error: {e} — retrying in 3s...")
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ollama connection error: {e} — retrying in 5s. Is Ollama running?")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Unexpected error: {e} — retrying in 3s...")
            time.sleep(3)

# Generic alias (replaces ask_groq)
ask_llm = ask_ollama

# === LOOP THROUGH EACH TEAM ===========================================
for TEAM_FOLDER in team_folders:
    team_name = os.path.basename(TEAM_FOLDER)
    print(f"\n{'='*70}")
    print(f"Processing {team_name} ...")
    print('='*70)

    # === Flexible file search helper ==================================
    def find_file(folder, patterns):
        for pattern in patterns:
            potential_path = os.path.join(folder, pattern)
            if os.path.exists(potential_path):
                return potential_path
        return None

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

    # === LOAD CACHE ===================================================
    # Helpful for re-running scripts without re-querying LLM for known commit messages
    if os.path.exists(CACHE_PATH):
        cache_df = pd.read_csv(CACHE_PATH)
        cache = dict(zip(cache_df["commit_message"], cache_df["event"]))
        print(f"[INFO] Loaded {len(cache)} cached commit analyses.")
    else:
        cache = {}

    # === LLM CALLER ===================================================
    # Call utility file
    def ask_groq(prompt, max_tokens=200):
        while True:
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": "You are a precise text classifier and explainer."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "rate" in err.lower():
                    print("⚠️ Rate-limit hit — sleeping 5s...")
                    time.sleep(5)
                    continue
                print(f"⚠️ Groq transient error: {err} — retrying in 3s...")
                time.sleep(3)

    # === LOAD CSVs ====================================================
    print("[INFO] Loading CSVs with parsed timestamps...")
    prs_df = pd.read_csv(PRS_PATH, parse_dates=["created_at"])
    commits_df = pd.read_csv(COMMITS_PATH)
    reviews_df = pd.read_csv(REVIEWS_PATH, parse_dates=["created_at"])
    print(f"[OK] PRs: {len(prs_df)} | Commits: {len(commits_df)} | Reviews: {len(reviews_df)}")

    # Normalize PR IDs
    for df_name, df in [("prs_df", prs_df), ("commits_df", commits_df), ("reviews_df", reviews_df)]:
        if "pr_id" in df.columns:
            df["pr_id"] = df["pr_id"].astype(str).str.extract(r"(\d+)")[0].astype("Int64")
            print(f"[DEBUG] Normalized pr_id in {df_name}: {df['pr_id'].nunique()} unique IDs")
            
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

    def classify_commit_message(msg):
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

    commits_df["event"] = [[] for _ in range(len(commits_df))]
    commits_df["llm_output"] = ""
    commits_df["llm_timestamp"] = ""

    for i, msg in enumerate(tqdm(commits_df["commit_message"].fillna(""))):
        label, llm_raw = classify_commit_message(msg)
        commits_df.at[i, "event"] = append_event(commits_df.at[i, "event"], label)
        commits_df.at[i, "llm_output"] = llm_raw
        commits_df.at[i, "llm_timestamp"] = RUN_TIMESTAMP if llm_raw else ""

    commits_df["main_label"] = "Communication"
    commits_df["created_at"] = commits_df["pr_id"].map(pr_time_lookup)

    # === STEP 2: PR LABELS ===========================================
    def label_pr(row): # --> rename function as "label_feature_doc" in communication
        """Label each PR based on merge status and documentation."""
        if pd.isna(row.get("merged_at")):
            return "no_merge"
        elif bool(row.get("docs_updated", False)):
            return "feature_documented"
        else:
            return "feature_undocumented"

    prs_df["event"] = [[] for _ in range(len(prs_df))]
    for i, row in prs_df.iterrows():
        # --- Base label: documentation / merge status ---
        base_label = label_pr(row)
        prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], base_label)
        num_reviewers = row.get("num_reviewers", 0)
        merged_at = row.get("merged_at", np.nan)
        # --- Handle different merge situations ---
        if pd.isna(merged_at):
            prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], "no_merge")
        else:
            merged_by = str(row.get("merged_by", "")).strip()
            pr_author = str(row.get("pr_author", "")).strip()

            if merged_by and pr_author and merged_by == pr_author:
                # same person merged their own PR
                prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], "self_merged")
            else:
                # merged by someone else (reviewed or otherwise)
                prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], "reviewed_merge")

    prs_df["llm_output"] = ""
    prs_df["llm_timestamp"] = ""
    prs_df["main_label"] = "Communication"
    prs_df["pr_author"] = prs_df.get("pr_author", "unknown")

    # === STEP 3: REVIEWS ==============================================
    print("[STEP 3] Evaluating review attributes and constructiveness...")

    review_counts = reviews_df.groupby("pr_id").size().reset_index(name="comment_count")
    reviews_df = reviews_df.merge(review_counts, on="pr_id", how="left")

    reviews_df["event"] = [[] for _ in range(len(reviews_df))]
    reviews_df["llm_output"] = ""
    reviews_df["llm_timestamp"] = ""
    reviews_df["main_label"] = "Communication"
    reviews_df["pr_author"] = reviews_df.get("user_login", "unknown")

    reviews_df["created_at"] = reviews_df["created_at"].combine_first(
        reviews_df["comment_id"].map(review_time_lookup) if "comment_id" in reviews_df.columns else pd.Series([pd.NaT]*len(reviews_df))
    )
    reviews_df["created_at"] = reviews_df["created_at"].combine_first(reviews_df["pr_id"].map(pr_time_lookup))
    
    
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

    for i, row in tqdm(reviews_df.iterrows(), total=len(reviews_df)):
        count = row.get("comment_count", 0)
        state = str(row.get("state", "")).lower().strip()
        if state == "changes_requested":
            reviews_df.at[i, "event"] = append_event(reviews_df.at[i, "event"], "changes_requested")
        elif state == "approved":
            reviews_df.at[i, "event"] = append_event(reviews_df.at[i, "event"], "empty_review_comment")

        comment = str(row.get("comment_body", "")).strip()
        if comment:
            llm_response = classify_constructiveness(comment)
            label = "constructive" if "constructive" in llm_response.lower() and "non" not in llm_response.lower() else "non_constructive"
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

    desc_labels = label_pr_descriptions(prs_df)

    # === STEP 5: AUTHOR + TIMESTAMP CLEANUP ===========================
    print("[STEP 5] Cleaning authors, timestamps, and sources...")

    def resolve_author(row):
        if pd.notna(row.get("pr_author")) and str(row["pr_author"]).strip():
            return row["pr_author"]
        if pd.notna(row.get("user_login")) and str(row["user_login"]).strip():
            return row["user_login"]
        return "unknown"

    for df in [commits_df, prs_df, reviews_df]:
        df["pr_author"] = df.apply(resolve_author, axis=1)
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["created_at"].fillna(method="ffill", inplace=True)

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

    # === integrated “script b” cleanup ================================
    if "author" in combined.columns and "pr_author" in combined.columns:
        combined["author"] = combined["author"].fillna(combined["pr_author"])
        combined = combined.dropna(subset=["author"])
        combined = combined.drop(columns=["pr_author"], errors="ignore")
        combined = combined.rename(columns={"author": "pr_author"})

    # === STEP 6.5: AUTHOR ANONYMIZATION & BOT FILTERING ===============
    print("[STEP 6.5] Applying anonymization and filtering out bots...")

    ANON_PATH = os.path.join(PROJECT_ROOT, "confidential", "anonymized_usernames.json")
    if os.path.exists(ANON_PATH):
        import json
        with open(ANON_PATH, "r") as f:
            anonym_map = json.load(f)
        print(f"[INFO] Loaded {len(anonym_map)} anonymized username mappings.")
    else:
        anonym_map = {}
        print("[WARN] anonymized_usernames.json not found — skipping anonymization.")

    before_len = len(combined)
    combined = combined[combined["pr_author"].str.lower() != "github-classroom[bot]"]
    after_len = len(combined)
    print(f"[INFO] Removed {before_len - after_len} rows from github-classroom[bot].")

    combined["pr_author"] = combined["pr_author"].apply(lambda x: anonym_map.get(str(x).strip(), x))

    # === STEP 7: SPLIT OUTPUTS (PR vs Communication) ==================
    PR_LABELS = {
        "self_merged", "reviewed_merge", "no_merge",
        "constructive_first_review", "constructive_second_review", "constructive_additional_review",
        "non_constructive_first_review", "non_constructive_second_review", "non_constructive_additional_review",
        "pr_description_clear", "pr_description_unclear", "changes_requested", "empty_review_comment"
    }

    COMM_LABELS = {
        "feature_documented", "feature_undocumented",
        "commit_informative", "commit_uninformative",
        "self_merged", "no_merge", "reviewed_merge"
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