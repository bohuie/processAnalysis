"""
Refactor Size Labeling: Small vs Large
Refactors are files with any deletions (regardless of additions).
Classified per file based on total lines modified.
"""
import pandas as pd


def label_refactor_size(commits_df, prs_df, pr_created_at_lookup, run_timestamp):
    """Label: small, large - Refactors calculated PER FILE based on lines modified."""
    result_rows = []
    
    if "file_path" not in commits_df.columns:
        print("    [WARN] No 'file_path' column in commits data.")
        print("    [INFO] Make sure you're loading '*_commit_file_changes.csv'")
        print("    [INFO] Skipping refactor analysis.")
        return pd.DataFrame()

    # Iterate per-file and mark as refactor if there are any deletions (regardless of additions)
    for _, row in commits_df.iterrows():
        pr_id = row.get("pr_id")
        commit_sha = row.get("commit_sha")
        filename = row.get("file_path", "unknown")

        additions = int(row.get("lines_added", 0) or 0)
        deletions = int(row.get("lines_deleted", 0) or 0)

        # Only consider files where at least one line was changed
        if additions == 0 and deletions == 0:
            continue

        # If there are no deletions, this is not a refactor (feature-only case handled elsewhere)
        if deletions == 0:
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
            "pr_author": pr_info.get("pr_author"),
            "created_at": created_at,
            "commit_sha": commit_sha,
            "filename": filename,
            "event": event,
            "main_label": "Refactor Size",
            "llm_output": f"rule-based: {refactor_lines} lines modified ({deletions}D+{additions}A) in {filename}",
            "llm_timestamp": run_timestamp
        })

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()