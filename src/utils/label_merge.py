def label_merge_state(prs_df):
    """Label: no_merge, self_merge, reviewed_merge - Determines how the PR was merged."""
    result_rows = []
    
    for _, row in prs_df.iterrows():
        pr_id = row["pr_id"]
        pr_author = row["pr_author"]
        merged_at = row.get("merged_at")
        created_at = row.get("created_at")
        
        merged_by_from_row = row.get("merged_by")
        
        if pd.isna(merged_at) or merged_at == '' or merged_at is None:
            event = "no_merge"
            llm_output = "rule-based: PR not merged"
        else:
            merged_by = str(merged_by_from_row).strip()
            pr_author_str = str(pr_author).strip()
            
            if merged_by and pr_author_str and merged_by.lower() == pr_author_str.lower(): 
                event = "self_merge"
                llm_output = f"rule-based: self-merged by {pr_author}"
            else:
                event = "reviewed_merge"
                merger_info = f"by {merged_by}" if merged_by else "(merger unknown)"
                llm_output = f"rule-based: merged {merger_info}"
        
        result_rows.append({
            "pr_id": pr_id,
            "pr_author": pr_author,
            "created_at": created_at,
            "merged_at": merged_at,
            "event": event,
            "main_label": "Merge State",
            "llm_output": llm_output,
            "llm_timestamp": RUN_TIMESTAMP
        })
    
    return pd.DataFrame(result_rows)