from pathlib import Path
import pandas as pd
import ast
import re

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = SCRIPT_DIR.parent / "data" / "csv"

team_folders = sorted(DATA_ROOT.glob("year-long-project-team-*"))
if not team_folders:
    raise FileNotFoundError(f"[ERROR] No team folders found in {DATA_ROOT}")

print(f"[INFO] Found {len(team_folders)} team folder(s):")
for f in team_folders:
    print(f"  → {f.name}")

for team_folder in team_folders:
    print(f"\n{'='*70}")
    print(f"[INFO] Processing: {team_folder.name}")
    print(f"{'='*70}")

    # find review-comments.csv file
    review_comment_files = sorted(team_folder.glob("year-long-project-team-*_review-comments.csv"))
    if not review_comment_files:
        print(f"[WARN] No review-comments.csv found in {team_folder}")
        continue

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

print(f"\n{'='*70}")
print("[COMPLETE] All matching review-comments.csv files cleaned.")
print(f"{'='*70}")


for team_folder in team_folders:
    team_name = team_folder.name
    print(f"\n{'='*70}")
    print(f"[INFO] Processing: {team_name}")
    print(f"{'='*70}")

    # Find matching files
    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if re.search(r"_PR_commits\.csv$", f.name, re.IGNORECASE)), None)
    prs_path = next((f for f in all_csvs if re.search(r"_all_pull_requests\.csv$", f.name, re.IGNORECASE)), None)
    review_comments_path = next((f for f in all_csvs if re.search(r"_review-comments\.csv$", f.name, re.IGNORECASE)), None)

    if not all([commits_path, prs_path, review_comments_path]):
        print(f"[WARN] Missing one or more required files for {team_name}, skipping.")
        continue

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

    # --- enrich PRs with top file metrics ---
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

    # --- fill order_of_review for comments ---
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
            .map({1: "first", 2: "second", 3: "additional", 4: "additional", 5: "additional", 6: "additional", 7: "additional", 8: "additional", 9: "additional", 10: "additional", 
                  11: "first", 12: "second", 13: "additional", 14: "additional", 15: "additional", 16: "additional", 17: "additional", 18: "additional", 19: "additional", 20: "additional"}) 
        )

    # --- save results ---
    enriched_prs.to_csv(prs_path, index=False)
    review_comments_df.to_csv(review_comments_path, index=False)

    print(f"[SUCCESS] Updated PRs saved to: {prs_path}")
    print(f"[SUCCESS] Updated review comments saved to: {review_comments_path}")
    print(f"[INFO] Final PR count: {len(enriched_prs)} | Final comments count: {len(review_comments_df)}")

print(f"\n{'='*70}")
print("[COMPLETE] All team folders processed!")
print(f"{'='*70}")