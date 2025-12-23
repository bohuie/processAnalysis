"""
Feature Size Labeling: Small vs Large
Features are files with additions and no deletions.
Classified per file based on lines added.
"""
import pandas as pd


def label_feature_size(commits_df, prs_df, pr_created_at_lookup, run_timestamp):
    """Label: small, large - Features calculated PER FILE.

    For each file-row in `commits_df` (expected to be the commit_file_changes CSV),
    classify the file as a Feature if it has additions and no deletions, and
    leave refactor classification to `label_refactor_size` which marks files with
    any deletions as refactors. This function therefore emits one row per file
    where deletions == 0 and additions > 0.
    """
    result_rows = []

    # Iterate file-level rows directly so labels are per-file (not aggregated per commit)
    for _, file_row in commits_df.iterrows():
        pr_id = file_row.get("pr_id")
        commit_sha = file_row.get("commit_sha")
        filename = file_row.get("file_path", "unknown")

        additions = int(file_row.get("lines_added", 0) or 0)
        deletions = int(file_row.get("lines_deleted", 0) or 0)

        # Only consider pure-addition files as features (no deletions)
        if deletions != 0 or additions == 0:
            continue

        pr_info = prs_df[prs_df["pr_id"] == pr_id]
        if pr_info.empty:
            continue
        pr_info = pr_info.iloc[0]

        event = "Small Feature Size" if additions < 50 else "Large Feature Size"
        created_at = pr_created_at_lookup.get(pr_id)

        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_info.get("pr_author"),
            "created_at": created_at,
            "commit_sha": commit_sha,
            "filename": filename,
            "event": event,
            "main_label": "Feature Size",
            "llm_output": f"rule-based: {additions} additions in {filename}",
            "llm_timestamp": run_timestamp
        })

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()