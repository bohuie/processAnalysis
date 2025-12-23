"""
Features Per Branch Labeling: One vs Multiple
Counts how many features (PRs) were created per branch.
"""
import pandas as pd


def create_branch_struct(prs_df):
    """Create a mapping of branch names to their PR IDs and authors."""
    branch_mapping = {}
    
    if "head_branch" not in prs_df.columns or "pr_id" not in prs_df.columns:
        return branch_mapping
    
    for _, row in prs_df.iterrows():
        branch_name = str(row.get("head_branch", "")).strip()
        pr_id = row.get("pr_id")
        pr_author = row.get("pr_author", "unknown")
        created_at = row.get("created_at")
        
        if not branch_name or pd.isna(pr_id):
            continue
            
        if branch_name not in branch_mapping:
            branch_mapping[branch_name] = []
        
        branch_mapping[branch_name].append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": created_at
        })
    
    return branch_mapping


def label_features_per_branch(prs_df, run_timestamp):
    """Label: one, multiple - Counts how many features (PRs) were created per branch."""
    result_rows = []
    
    branch_mapping = create_branch_struct(prs_df)
    
    for branch_name, pr_list in branch_mapping.items():
        count = len(pr_list)
        
        event = "one Features Per Branch" if count == 1 else "multiple Features Per Branch"
        
        for pr_info in pr_list:
            result_rows.append({
                "pr_id": pr_info["pr_id"],
                "pr_author": pr_info["pr_author"],
                "created_at": pr_info.get("created_at"),
                "branch_name": branch_name,
                "event": event,
                "main_label": "Features Per Branch",
                "llm_output": f"rule-based: {count} feature(s) on branch '{branch_name}'",
                "llm_timestamp": run_timestamp
            })
    
    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()