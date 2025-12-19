"""
Repository Status Labeling: Up-to-date vs Outdated
Determines if PR branch was up-to-date with base at merge time.
"""
import pandas as pd


def label_repo_status(prs_df, run_timestamp):
    """Label: up-to-date, outdated - Determines if PR branch was up-to-date with base."""
    result_rows = []

    if "was_up_to_date_at_merge" not in prs_df.columns:
        print("Column 'was_up_to_date_at_merge' not found in dataframe.")
        return pd.DataFrame()

    print("Generating repository status labels based on 'was_up_to_date_at_merge'...")

    for _, row in prs_df.iterrows():
        pr_id = row.get("pr_id")
        was_up_to_date = row.get("was_up_to_date_at_merge", None)

        if isinstance(was_up_to_date, str):
            was_up_to_date = was_up_to_date.strip().lower()
            if was_up_to_date == "true":
                was_up_to_date = True
            elif was_up_to_date == "false":
                was_up_to_date = False
            else:
                was_up_to_date = None

        if pd.isna(was_up_to_date) or was_up_to_date is None:
            continue

        if was_up_to_date is True:
            event = "up-to-date"
            llm_output = "rule-based: was_up_to_date_at_merge=True"
        else:
            event = "outdated"
            conflicts = row.get("has_conflicts", "N/A")
            llm_output = f"rule-based: was_up_to_date_at_merge=False (conflicts={conflicts})"

        result_rows.append({
            "pr_id": pr_id,
            "pr_author": row.get("pr_author"),
            "created_at": row.get("created_at"),
            "event": event,
            "main_label": "Repository Status",
            "llm_output": llm_output,
            "llm_timestamp": run_timestamp
        })

    print(f"Generated {len(result_rows)} repository status labels")

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()