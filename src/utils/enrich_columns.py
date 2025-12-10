def enrich_prs_and_comments(team_folder):
    """Enrich PRs with top file metrics and add order_of_review to comments."""
    team_name = team_folder.name
    print(f"\n{'='*70}")
    print(f"[INFO] Enriching data for: {team_name}")
    print(f"{'='*70}")

    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if f.name.endswith("_PR_commits.csv")), None)
    prs_path = next((f for f in all_csvs if f.name.endswith("_all_pull_requests.csv")), None)
    review_comments_path = next((f for f in all_csvs if f.name.endswith("_review-comments.csv")), None)

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

    # --- FIX START: Handle MergeError on rerun ---
    # Drop existing enrichment columns before merge to avoid conflicts if the script is re-run
    enrichment_cols = ["top_file", "top_file_change_%", "docs_updated"]
    for col in enrichment_cols:
        if col in prs_df.columns:
            print(f"[INFO] Dropping existing enrichment column: {col}")
            prs_df = prs_df.drop(columns=[col])
    # --- FIX END ---

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