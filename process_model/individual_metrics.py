"""
individual_metrics.py

Generates per-developer metrics from cleaned PR and review-comment logs.
Metrics are anonymized by design and intended to characterize how work and
review activity are distributed within teams, not to evaluate individuals.

Notes:
- Review activity is inferred from review comments only; silent approvals
  are not captured.
- Metrics are computed from CLEAN_ CSVs and may differ slightly from
  GitHub UI counts due to filtering and missing timestamps.
"""
import os
import glob
import pandas as pd
import numpy as np
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
FOLDER_SOURCE = os.getenv("FOLDER_SOURCE", "pr")

def normalize_username(user_series):
    """Normalize username to lowercase string, handling mixed types."""
    return user_series.fillna("").astype(str).str.lower().str.strip()

def safe_div(n, d):
    return n / d if d > 0 else 0.0

def load_team_data(team_dir):
    """
    Load PR and review data for a specific team directory.
    Returns tuple of (pr_df, review_df) or (None, None) if files missing.
    """
    team_name = os.path.basename(team_dir)
    
    pr_file = os.path.join(team_dir, f"CLEAN_{team_name}_all_pull_requests.csv")
    review_file = os.path.join(team_dir, f"CLEAN_{team_name}_review-comments.csv")
    
    if not os.path.exists(pr_file):
        print(f"[WARN] PR file not found for {team_name}: {pr_file}")
        return None, None
        
    if not os.path.exists(review_file):
        print(f"[WARN] Review file not found for {team_name}: {review_file}. Continuing with empty review data.")
        review_df = pd.DataFrame(columns=['pr_id', 'author', 'created_at', 'state'])
    else:
        try:
            review_df = pd.read_csv(review_file)
        except Exception as e:
             print(f"[ERROR] Failed to read review file {review_file}: {e}")
             review_df = pd.DataFrame(columns=['pr_id', 'author', 'created_at', 'state'])

    try:
        pr_df = pd.read_csv(pr_file)
    except Exception as e:
        print(f"[ERROR] Failed to read PR file {pr_file}: {e}")
        return None, None

    return pr_df, review_df

def process_team(team_dir):
    """Process a single team's data and return a DataFrame of individual metrics."""
    team_number = os.path.basename(team_dir).replace("year-long-project-team-", "")
    
    pr_df, review_df = load_team_data(team_dir)
    if pr_df is None:
        return pd.DataFrame()

    # --- Preprocessing ---
    
    # Normalize usernames
    # pr_author in PRs, author in reviews
    if 'pr_author' in pr_df.columns:
        pr_df['pr_author'] = normalize_username(pr_df['pr_author'])
    else:
        print(f"[ERROR] 'pr_author' column missing in PR data for team {team_number}")
        return pd.DataFrame()

    if 'author' in review_df.columns:
        review_df['author'] = normalize_username(review_df['author'])
    else:
        # Fallback if empty or malformed
        review_df['author'] = "" # Should effectively be empty

    # Parse Dates
    date_cols_pr = ['created_at', 'closed_at', 'merged_at', 'updated_at']
    for col in date_cols_pr:
        if col in pr_df.columns:
            pr_df[col] = pd.to_datetime(pr_df[col], utc=True, errors='coerce')
    
    if 'created_at' in review_df.columns:
        review_df['created_at'] = pd.to_datetime(review_df['created_at'], utc=True, errors='coerce')

    # Identify all developers (authors union reviewers)
    authors = set(pr_df['pr_author'].unique())
    reviewers = set(review_df['author'].unique())
    all_devs = sorted(list(authors.union(reviewers)))
    all_devs = [d for d in all_devs if d] # Remove empty strings

    metrics_list = []

    for dev in all_devs:
        # Filter data for this developer
        authored_prs = pr_df[pr_df['pr_author'] == dev]
        
        # Reviews BY this developer (on OTHER peoples' PRs usually, but we count all actions)
        # Note: prs_reviewed definition: number of distinct PRs reviewed
        dev_reviews = review_df[review_df['author'] == dev]
        
        # --- A) Activity / Volume ---
        prs_authored = len(authored_prs)
        prs_reviewed = dev_reviews['pr_id'].nunique() if 'pr_id' in dev_reviews.columns else 0
        review_comments = len(dev_reviews)
        
        # Active Days calculation
        # Gather all timestamps from PR creation and Review creation
        t_authored = authored_prs['created_at'].dropna()
        t_reviewed = dev_reviews['created_at'].dropna()
        all_timestamps = pd.concat([t_authored, t_reviewed])
        if not all_timestamps.empty:
            active_days = all_timestamps.dt.date.nunique()
        else:
            active_days = 0

        # --- B) Outcomes (Authored PRs) ---
        # merged_at is not null -> merged
        # OR state == 'merged'
        # closed_no_merge: state == 'closed' AND merged_at is null
        
        merges_authored = 0
        closed_no_merge_authored = 0
        
        if 'merged_at' in authored_prs.columns and 'state' in authored_prs.columns:
            # Merged
            merges_authored = authored_prs[
                (authored_prs['merged_at'].notna()) | 
                (authored_prs['state'].str.lower() == 'merged')
            ].shape[0]
            
            # Closed without merge
            # Strictly: closed state AND no merged_at timestamp
            closed_no_merge_authored = authored_prs[
                (authored_prs['state'].str.lower() == 'closed') & 
                (authored_prs['merged_at'].isna())
            ].shape[0]

        if prs_authored > 0:
            merge_rate_authored = merges_authored / prs_authored
        else:
            merge_rate_authored = np.nan

        # --- Role Hint ---
        # Heuristic: ratio of authored vs reviewed
        total_actions = prs_authored + prs_reviewed
        if total_actions == 0:
            role_hint = "inactive"
        else:
            ratio = prs_authored / total_actions
            if ratio >= 0.66: # Mostly authoring (2/3+)
                role_hint = "author-heavy"
            elif ratio <= 0.33: # Mostly reviewing (2/3+)
                role_hint = "review-heavy"
            else:
                role_hint = "mixed"

        # --- C) Timing (Authored PRs) ---
        avg_pr_lifetime_hours = np.nan
        avg_time_to_first_review_hours = np.nan
        
        # PR Lifetime
        # If merged: merged_at - created_at
        # If closed (unmerged): closed_at - created_at
        # We can just take the first non-null of merged_at/closed_at as 'end_time'
        # created_at must exist
        
        # Vectorized approach for lifetime
        if not authored_prs.empty and 'created_at' in authored_prs.columns and 'closed_at' in authored_prs.columns and 'merged_at' in authored_prs.columns:
            # Prefer merged_at, fallback to closed_at
            end_times = authored_prs['merged_at'].combine_first(authored_prs['closed_at'])
            lifetimes = end_times - authored_prs['created_at']
            # Convert to hours
            lifetimes_hours = lifetimes.dt.total_seconds() / 3600.0
            avg_pr_lifetime_hours = lifetimes_hours.mean()

        # Time to first review
        # For each authored PR, find earliest review timestamp from OTHER users
        if not authored_prs.empty and not review_df.empty and 'created_at' in authored_prs.columns and 'created_at' in review_df.columns:
            # Filter reviews to exclude self-reviews (comments on own PR)
            authored_pr_ids = authored_prs['pr_id'].unique()
            
            # Reviews on these PRs, NOT by the author
            relevant_reviews = review_df[
                (review_df['pr_id'].isin(authored_pr_ids)) & 
                (review_df['author'] != dev)
            ]
            
            if not relevant_reviews.empty:
                # Find first review time per PR
                first_reviews = relevant_reviews.groupby('pr_id')['created_at'].min().reset_index()
                first_reviews.columns = ['pr_id', 'first_review_at']
                
                # Merge back to authored_prs to get creation time
                pr_times = authored_prs[['pr_id', 'created_at']].merge(first_reviews, on='pr_id', how='inner')
                
                if not pr_times.empty:
                    ttfr = pr_times['first_review_at'] - pr_times['created_at']
                    ttfr_hours = ttfr.dt.total_seconds() / 3600.0
                    # Filter out negative times
                    ttfr_hours = ttfr_hours[ttfr_hours >= 0]
                    avg_time_to_first_review_hours = ttfr_hours.mean()

        # --- D) Review Dynamics ---
        # avg_review_rounds_authored: count of distinct review submissions (timestamps/IDs) 
        # on authored PRs where state is 'APPROVED' or 'CHANGES_REQUESTED'
        avg_review_rounds_authored = np.nan
        if not authored_prs.empty and not review_df.empty and 'state' in review_df.columns:
            authored_pr_ids = authored_prs['pr_id'].unique()
            decisive_reviews = review_df[
                (review_df['pr_id'].isin(authored_pr_ids)) &
                (review_df['state'].isin(['APPROVED', 'CHANGES_REQUESTED']))
            ]
            
            if not decisive_reviews.empty:
                # We want average rounds per PR.
                # Count events per PR
                rounds_per_pr = decisive_reviews.groupby('pr_id').size()
                all_pr_counts = pd.Series(0, index=authored_prs['pr_id'].unique())
                all_pr_counts = all_pr_counts.add(rounds_per_pr, fill_value=0)
                
                avg_review_rounds_authored = all_pr_counts.mean()
            else:
                avg_review_rounds_authored = 0.0
        elif not authored_prs.empty:
             avg_review_rounds_authored = 0.0

        metrics_list.append({
            'team_number': team_number,
            'developer': dev,
            'role_hint': role_hint,
            'prs_authored': prs_authored,
            'prs_reviewed': prs_reviewed,
            'review_comments': review_comments,
            'active_days': active_days,
            'merges_authored': merges_authored,
            'closed_no_merge_authored': closed_no_merge_authored,
            'merge_rate_authored': round(merge_rate_authored, 3),
            'avg_time_to_first_review_hours': round(avg_time_to_first_review_hours, 2),
            'avg_pr_lifetime_hours': round(avg_pr_lifetime_hours, 2),
            'avg_review_rounds_authored': round(avg_review_rounds_authored, 2)
        })

    return pd.DataFrame(metrics_list)

def main():
    # Setup paths
    base_data_dir = os.path.join("data", "csv")
    output_dir = os.path.join("data", "outputs", FOLDER_SOURCE)
    
    # 1. Identify teams
    search_path = os.path.join(base_data_dir, "year-long-project-team-*")
    team_dirs = glob.glob(search_path)
    
    print(f"[INFO] Source Folder: {base_data_dir}")
    print(f"[INFO] Output Folder: {output_dir}")
    print(f"[INFO] Found {len(team_dirs)} team directories.")
    
    all_metrics = []
    
    for team_dir in team_dirs:
        # Check if dir
        if not os.path.isdir(team_dir):
            continue
            
        print(f"Processing {os.path.basename(team_dir)}...")
        df = process_team(team_dir)
        if not df.empty:
            all_metrics.append(df)
            
    if all_metrics:
        final_df = pd.concat(all_metrics, ignore_index=True)
        
        # Ensure Output Directory Exists
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, "individual_metrics.csv")
        final_df.to_csv(output_path, index=False)
        print(f"\n[SUCCESS] Generated metrics for {len(final_df)} developers across {final_df['team_number'].nunique()} teams.")
        print(f"Output saved to: {output_path}")
        
        # Preview
        print("\nPreview:")
        print(final_df.head().to_string())
    else:
        print("\n[WARN] No metrics generated. Check data directories and file names.")

if __name__ == "__main__":
    main()
