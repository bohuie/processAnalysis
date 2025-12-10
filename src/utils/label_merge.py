from __future__ import annotations

import pandas as pd


def label_merge_state(prs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create merge-state labels for each PR.

    For every row in prs_df, produces a label in:
        - 'no_merge'
        - 'self_merge'
        - 'reviewed_merge'

    Returns a new DataFrame with columns:
        - pr_id
        - pr_author
        - created_at
        - merged_at
        - event       (no_merge/self_merge/reviewed_merge)
        - main_label  ("Merge State")
    """
    required_cols = {"pr_id", "pr_author", "created_at", "merged_at"}
    missing = required_cols - set(prs_df.columns)
    if missing:
        raise KeyError(f"label_merge_state: missing columns {missing}")

    result_rows = []

    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        merged_at = row.get("merged_at")
        created_at = row.get("created_at")
        merged_by_from_row = row.get("merged_by")

        # --- core logic ---
        if pd.isna(merged_at) or merged_at == "" or merged_at is None:
            event = "no_merge"
        else:
            merged_by = str(merged_by_from_row).strip()
            pr_author_str = str(pr_author).strip()

            if merged_by and pr_author_str and merged_by.lower() == pr_author_str.lower():
                event = "self_merge"
            else:
                event = "reviewed_merge"

        result_rows.append(
            {
                "pr_id": pr_id,
                "pr_author": pr_author,
                "created_at": created_at,
                "merged_at": merged_at,
                "event": event,
                "main_label": "Merge State",
            }
        )

    return pd.DataFrame(result_rows)
