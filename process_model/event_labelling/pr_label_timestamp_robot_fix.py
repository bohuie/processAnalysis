import os
import glob
import pandas as pd
from datetime import timedelta

# -------------------------------------------------------------------
# REVIEW LABELS THAT NEED TIMESTAMP FIXING
# -------------------------------------------------------------------
REVIEW_LABELS = {
    "non_constructive_first_review",
    "non_constructive_second_review",
    "non_constructive_additional_review",
    "constructive_first_review",
    "constructive_second_review",
    "constructive_additional_review"
}

# -------------------------------------------------------------------
# PATH CONFIG
# -------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
CSV_DIR = os.path.join(BASE_DIR, "data", "csv")

# -------------------------------------------------------------------
# FIND ALL pr_labels FILES
# -------------------------------------------------------------------
pr_label_files = sorted(glob.glob(os.path.join(CSV_DIR, "pr_labels_year-long-project-team-*.csv")))

if not pr_label_files:
    raise FileNotFoundError("❌ No pr_labels_*.csv files found.")

print(f"[INFO] Found {len(pr_label_files)} pr_labels files.")

# -------------------------------------------------------------------
# PROCESS EACH TEAM
# -------------------------------------------------------------------
for pr_label_path in pr_label_files:

    team_name = os.path.basename(pr_label_path).replace("pr_labels_", "").replace(".csv", "")
    team_folder = os.path.join(CSV_DIR, team_name)

    pr_csv_path = os.path.join(team_folder, f"{team_name}_all_pull_requests.csv")

    if not os.path.exists(pr_csv_path):
        print(f"⚠️ Missing all_pull_requests.csv for {team_name}, skipping.")
        continue

    print(f"\n=== Processing {team_name} ===")
    print(f"[INFO] pr_labels: {pr_label_path}")
    print(f"[INFO] PR metadata: {pr_csv_path}")

    # -------------------------------------------------------------------
    # LOAD FILES
    # -------------------------------------------------------------------
    df = pd.read_csv(pr_label_path)
    pr_df = pd.read_csv(pr_csv_path)

    # Ensure timestamps are parsed properly
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    pr_df["created_at"] = pd.to_datetime(pr_df["created_at"], errors="coerce")

    # -------------------------------------------------------------------
    # REMOVE BOT PRs COMPLETELY
    # -------------------------------------------------------------------
    bot_pr_ids = pr_df.loc[
        pr_df["pr_author"].astype(str).str.lower() == "github-classroom[bot]",
        "pr_id"
    ].tolist()

    if bot_pr_ids:
        before = len(df)
        df = df[~df["pr_id"].isin(bot_pr_ids)].reset_index(drop=True)
        after = len(df)
        print(f"[INFO] Removed {before - after} rows belonging to PRs authored by github-classroom[bot].")
    else:
        print("[INFO] No bot-authored PRs found.")

    # -------------------------------------------------------------------
    # BUILD pr_id → timezone offset hours lookup
    # -------------------------------------------------------------------
    pr_offset = {}

    for _, row in pr_df.iterrows():
        prid = row.get("pr_id")
        created_at = str(row.get("created_at"))

        # Extract timezone component manually, e.g. "-07:00"
        if "-" in created_at[-6:] or "+" in created_at[-6:]:
            tz = created_at[-6:]  # e.g., "-07:00"
            try:
                hours = int(tz[1:3])  # number part (07 or 08)
                pr_offset[prid] = hours
            except:
                continue

    print(f"[INFO] Built offset lookup for {len(pr_offset)} PRs.")

    # -------------------------------------------------------------------
    # FIX TIMESTAMPS FOR REVIEW ROWS *ONLY IF comment_id IS EMPTY*
    # -------------------------------------------------------------------
    fixed_count = 0

    for i, row in df.iterrows():

        events = row.get("event", "")
        pr_id = row.get("pr_id")

        # --- NEW RULE: Skip if comment_id has a value ---
        comment_id = row.get("comment_id")
        if pd.notna(comment_id) and str(comment_id).strip() != "":
            continue  # leave timestamp unchanged

        # Must be one of the review labels
        if not isinstance(events, str):
            continue
        if not any(label in events for label in REVIEW_LABELS):
            continue

        offset_hours = pr_offset.get(pr_id)
        if offset_hours is None:
            continue

        if pd.notna(row["created_at"]):
            df.at[i, "created_at"] = row["created_at"] + timedelta(hours=offset_hours)
            fixed_count += 1

    print(f"[SUCCESS] Adjusted {fixed_count} timestamps for {team_name}.")

    # -------------------------------------------------------------------
    # SAVE UPDATED FILE
    # -------------------------------------------------------------------
    df.to_csv(pr_label_path, index=False)
    print(f"[SAVED] Updated file → {pr_label_path}")

print("\n=== COMPLETE: All review timestamps updated. ===")

