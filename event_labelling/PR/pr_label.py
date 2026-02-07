import os
import glob
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from datetime import datetime
from process_model.clean import create_clean_pr_label_csv

# utility imports
from src.utils.normalize_pr_id import normalize_pr_ids
from src.utils.label_merge import label_merge_state

# helper imports
from event_labelling.PR.helpers_pr import (
    append_event,
    find_file,
)
from event_labelling.PR.prep_data import (
    preprocess_team_csvs,
)
from event_labelling.PR.review_helper import (
    label_review_constructiveness,)

# llm prompt imports
from event_labelling.PR.llm_prompts import (
    label_pr_descriptions,
)


# == GLOBALS ==========================================================
PRS_PATTERN_TEMPLATES = [
    "{team}_all_pull_requests.csv",
    "{team}_PRs.csv",
    "all_pull_requests.csv",
]

COMMITS_PATTERN_TEMPLATES = [
    "{team}_PR_commits.csv",
    "{team}_commits.csv",
    "PR_commits.csv",
]

REVIEWS_PATTERN_TEMPLATES = [
    "{team}_review-comments.csv",
    "review-comments.csv",
]

PR_LABELS = {
            "self_merge", "reviewed_merge", "no_merge",
            "constructive_first_review", "constructive_second_review", "constructive_additional_review",
            "non_constructive_first_review", "non_constructive_second_review", "non_constructive_additional_review",
            "pr_description_clear", "pr_description_unclear", "changes_requested", "approved_empty_review"
}


# === SETUP ============================================================
load_dotenv()

RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data", "csv")
os.makedirs(DATA_FOLDER, exist_ok=True)
CACHE_PATH = os.path.join(DATA_FOLDER, "commit_message_cache.csv")

PR_LOOKUP_PATH = os.path.join(DATA_FOLDER, "pr_timestamp_lookup.csv")
REVIEW_LOOKUP_PATH = os.path.join(DATA_FOLDER, "review_timestamp_lookup.csv")


def process_all_teams() -> None:
    """Main driver: preprocess CSVs and generate PR labels for all teams."""
    # === FIND ALL TEAM FOLDERS =======================================
    team_folders = glob.glob(os.path.join(DATA_FOLDER, "year-long-project-team-*"))
    if not team_folders:
        raise FileNotFoundError(f"❌ No team folders found in {DATA_FOLDER}")

    print(f"[INFO] Found {len(team_folders)} team folders:")
    for t in team_folders:
        print(" -", os.path.basename(t))

    # === MAIN LOOP: EACH TEAM ========================================
    for TEAM_FOLDER in team_folders:
        team_name = os.path.basename(TEAM_FOLDER)
        print(f"\n{'='*70}")
        print(f"Processing {team_name} ...")
        print('='*70)

        prs_patterns = [p.format(team=team_name) for p in PRS_PATTERN_TEMPLATES]
        commits_patterns = [p.format(team=team_name) for p in COMMITS_PATTERN_TEMPLATES]
        reviews_patterns = [p.format(team=team_name) for p in REVIEWS_PATTERN_TEMPLATES]

        # === Locate files =============================================
        PRS_PATH = find_file(TEAM_FOLDER, prs_patterns)
        COMMITS_PATH = find_file(TEAM_FOLDER, commits_patterns)
        REVIEWS_PATH = find_file(TEAM_FOLDER, reviews_patterns)

        # === Output path ==============================================
        OUTPUT_PATH = os.path.join(DATA_FOLDER, f"pr_communications_labels_{team_name}.csv")

        # === Validate file existence =================================
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
        
        # === PREPROCESS RAW CSVs (bots, logs, review filters, order_of_review, anonymize) ===
        clean_prs_path, clean_commits_path, clean_reviews_path = preprocess_team_csvs(
            team_folder=TEAM_FOLDER,
            team_name=team_name,
            prs_path=PRS_PATH,
            commits_path=COMMITS_PATH,
            reviews_path=REVIEWS_PATH,
        )

        # === LOAD CSVs (already preprocessed) =========================
        print("[INFO] Loading CSVs with parsed timestamps...")
        prs_df = pd.read_csv(clean_prs_path, parse_dates=["created_at"])
        commits_df = pd.read_csv(clean_commits_path)
        reviews_df = pd.read_csv(clean_reviews_path, parse_dates=["created_at"])
        print(f"[OK] CLEAN PRs: {len(prs_df)} | CLEAN Commits: {len(commits_df)} | CLEAN Reviews: {len(reviews_df)}")

        # === Normalize PR IDs ========================================
        named_dfs = [
            ("prs_df", prs_df),
            ("commits_df", commits_df),
            ("reviews_df", reviews_df),
        ]
        normalize_pr_ids(named_dfs)
        prs_df, commits_df, reviews_df = [df for _, df in named_dfs]


        # === STEP 0: LOOKUPS ==========================================
        print("[STEP 0] Building timestamp lookups...")
        pr_lookup = (
            prs_df[["pr_id", "created_at"]]
            .dropna(subset=["pr_id", "created_at"])
            .drop_duplicates(subset=["pr_id"])
        )
        pr_time_lookup = pr_lookup.set_index("pr_id")["created_at"].to_dict()
        pr_lookup.to_csv(PR_LOOKUP_PATH, index=False)

        if "comment_id" in reviews_df.columns:
            review_lookup = (
                reviews_df[["comment_id", "created_at"]]
                .dropna(subset=["comment_id", "created_at"])
                .drop_duplicates(subset=["comment_id"])
            )
            review_time_lookup = review_lookup.set_index("comment_id")["created_at"].to_dict()
            review_lookup.to_csv(REVIEW_LOOKUP_PATH, index=False)
        else:
            review_time_lookup = {}

        # === STEP 2: MERGE LABELS =======================================
        print("[STEP 2] Labelling PRs (merge state)...")

        prs_df["event"] = [[] for _ in range(len(prs_df))]
        merge_labels_df = label_merge_state(prs_df)
        merge_event_map = merge_labels_df.set_index("pr_id")["event"].to_dict()

        for i, row in prs_df.iterrows():
            pr_id = row.get("pr_id")
            merge_event = merge_event_map.get(pr_id)
            if merge_event:
                prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], merge_event)
        prs_df["pr_author"] = prs_df.get("pr_author", "unknown")

        # === STEP 3: REVIEWS ==========================================
        print("[STEP 3] Evaluating review attributes and constructiveness...")
        reviews_df = label_review_constructiveness(
            reviews_df=reviews_df,
            pr_time_lookup=pr_time_lookup,
            review_time_lookup=review_time_lookup,
            run_timestamp=RUN_TIMESTAMP,
        )

        # === STEP 4: PR DESCRIPTION ===================================
        desc_labels = label_pr_descriptions(prs_df)

        commits_df["source"] = "commit"
        prs_df["source"] = "pr"
        reviews_df["source"] = "review"

        # === STEP 6: COMBINE + FINAL CLEANUP ==========================
        print("[STEP 6] Combining and final cleanup...")

        combined = pd.concat([commits_df, prs_df, reviews_df, desc_labels], ignore_index=True)
        combined["created_at"] = pd.to_datetime(combined["created_at"], errors="coerce")
        combined["created_at"].fillna(method="ffill", inplace=True)

        # Keep pr_author as-is; just clean empties
        if "pr_author" in combined.columns:
            combined["pr_author"].replace("", np.nan, inplace=True)
            combined["pr_author"].fillna("unknown", inplace=True)

        combined = combined.sort_values("created_at").reset_index(drop=True)

        pr_rows = []

        for _, row in combined.iterrows():
            ev_val = row["event"]

            # Normalize to a list of strings
            if isinstance(ev_val, list):
                evs = [e for e in ev_val if isinstance(e, str)]
            elif isinstance(ev_val, str):
                # Single label stored as a string
                evs = [ev_val]
            else:
                # NaN or anything else → no events
                evs = []

            pr_evs = [e for e in evs if e in PR_LABELS]

            if pr_evs:
                new_row = row.copy()
                new_row["event"] = str(pr_evs)
                pr_rows.append(new_row)

        pr_df = pd.DataFrame(pr_rows)

        # === SAVE FILES ===========================================
        PR_OUTPUT_PATH = os.path.join(DATA_FOLDER, f"pr_labels_{team_name}.csv")

        if not pr_df.empty:
            pr_df.to_csv(PR_OUTPUT_PATH, index=False)
            print(f"[OK] PR labels saved → {PR_OUTPUT_PATH} ({len(pr_df)} rows)")

            create_clean_pr_label_csv(PR_OUTPUT_PATH)

        else:
            print("[WARN] No PR labels found to save.")


if __name__ == "__main__":
    process_all_teams()
