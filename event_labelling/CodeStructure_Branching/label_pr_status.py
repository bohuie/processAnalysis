"""
PR Status Labeling: Closed, Still Open, or Merged
Determines the current status of the PR.
"""
import pandas as pd


def label_pr_status(prs_df, run_timestamp):
    """Label: closed, still_open, merged - Determines current status of the PR."""
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        state = row.get("state", "")
        merged_at = row.get("merged_at", None)
        
        if pd.isna(state):
            state = ""
        else:
            state = str(state).lower()
        
        if state == "open":
            event = "still_open"
            llm_output = "rule-based: currently open"
        elif state == "closed" and merged_at is not None and pd.notna(merged_at) and merged_at != "":
            event = "merged"
            llm_output = "rule-based: closed and merged"
        elif state == "closed":
            event = "closed"
            llm_output = "rule-based: closed without merge"
        else:
            event = "unknown"
            llm_output = f"rule-based: unknown state '{state}', treating as unknown"
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": row.get("created_at"),
            "event": event,
            "main_label": "PR Status",
            "llm_output": llm_output,
            "llm_timestamp": run_timestamp
        })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()