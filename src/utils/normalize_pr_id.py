    # Normalize PR IDs
    for df_name, df in [("prs_df", prs_df), ("commits_df", commits_df), ("reviews_df", reviews_df)]:
        if "pr_id" in df.columns:
            df["pr_id"] = df["pr_id"].astype(str).str.extract(r"(\d+)")[0].astype("Int64")
            print(f"[DEBUG] Normalized pr_id in {df_name}: {df['pr_id'].nunique()} unique IDs")