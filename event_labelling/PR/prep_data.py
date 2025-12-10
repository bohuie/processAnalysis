import pandas as pd
from src.utils.anonymize_columns import (
    anonymize_author_columns,)
from src.utils.enrich_columns import add_order_of_review

# helper imports
from event_labelling.PR.helpers_pr import (
    drop_bots_in_author_like_columns,
    drop_log_rows,)


# ---------------------------------------------------------------------
# Combined preprocessing for STEP -1A ... STEP -1B/E
# ---------------------------------------------------------------------

def _apply_review_specific_filters(raw_reviews_df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """
    Apply the review-specific filters:
      - Remove rows where author == pr_author
      - Remove rows where comment_type == 'review' AND empty comment_body AND state == 'COMMENTED'
      - Remove rows where comment_type == 'conversation'
    """
    # 3a) Remove rows where author == pr_author
    if {"author", "pr_author"} <= set(raw_reviews_df.columns):
        before = len(raw_reviews_df)
        mask = raw_reviews_df["author"].astype(str) != raw_reviews_df["pr_author"].astype(str)
        raw_reviews_df = raw_reviews_df[mask].copy()
        removed = before - len(raw_reviews_df)
        print(f"[STEP -1C] {team_name} Reviews: removed {removed} rows where author == pr_author")
    else:
        print("[STEP -1C] Reviews: author/pr_author not both present; skipping self-review filter.")

    # 3b) Remove rows where comment_type == 'review' AND empty comment_body AND state == 'COMMENTED'
    if {"comment_type", "comment_body", "state"} <= set(raw_reviews_df.columns):
        before = len(raw_reviews_df)
        ct = raw_reviews_df["comment_type"].astype(str).str.lower()
        body_empty = raw_reviews_df["comment_body"].astype(str).str.strip().eq("")
        state = raw_reviews_df["state"].astype(str).str.upper()
        cond = (ct.eq("review") & body_empty & state.eq("COMMENTED"))
        raw_reviews_df = raw_reviews_df[~cond].copy()
        removed = before - len(raw_reviews_df)
        print(f"[STEP -1D] {team_name} Reviews: removed {removed} empty COMMENTED review rows")
    else:
        print("[STEP -1D] Reviews: missing comment_type/comment_body/state; skipping empty review filter.")

    # 3c) Remove rows where comment_type == 'conversation'
    if "comment_type" in raw_reviews_df.columns:
        before = len(raw_reviews_df)
        conv_mask = raw_reviews_df["comment_type"].astype(str).str.lower().eq("conversation")
        raw_reviews_df = raw_reviews_df[~conv_mask].copy()
        removed = before - len(raw_reviews_df)
        print(f"[STEP -1E] {team_name} Reviews: removed {removed} 'conversation' comments")
    else:
        print("[STEP -1E] Reviews: no comment_type column; skipping conversation filter.")

    return raw_reviews_df


def preprocess_team_csvs(
    team_folder: str,
    team_name: str,
    prs_path: str,
    commits_path: str,
    reviews_path: str,
) -> None:
    print("[STEP -1A] Loading raw CSVs for preprocessing...")
    raw_prs_df = pd.read_csv(prs_path)
    raw_commits_df = pd.read_csv(commits_path)
    raw_reviews_df = pd.read_csv(reviews_path)

    # 1) Remove bots
    raw_prs_df = drop_bots_in_author_like_columns(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_bots_in_author_like_columns(raw_commits_df, f"{team_name} Commits")
    raw_reviews_df = drop_bots_in_author_like_columns(raw_reviews_df, f"{team_name} Reviews")

    # 2) Remove rows mentioning logs/log
    raw_prs_df = drop_log_rows(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_log_rows(raw_commits_df, f"{team_name} Commits")
    raw_reviews_df = drop_log_rows(raw_reviews_df, f"{team_name} Reviews")

    # 3) Review-specific filters BEFORE order_of_review
    raw_reviews_df = _apply_review_specific_filters(raw_reviews_df, team_name)

    # 4) Overwrite the CSVs with cleaned (still de-anonymized) data
    raw_prs_df.to_csv(prs_path, index=False)
    raw_commits_df.to_csv(commits_path, index=False)
    raw_reviews_df.to_csv(reviews_path, index=False)

    # 5) Add order_of_review to review comments (reviewer-based logic)
    print("[STEP -1F] Adding order_of_review to review-comments via enrichment utility...")
    add_order_of_review(team_folder)

    # 6) Reload CSVs (now including order_of_review in reviews)
    print("[STEP -1G] Anonymizing author columns on disk...")
    prs_df = pd.read_csv(prs_path)
    commits_df = pd.read_csv(commits_path)
    reviews_df = pd.read_csv(reviews_path)

    # Pass actual DataFrames, not paths
    anonymize_author_columns([
        ("prs", prs_df),
        ("commits", commits_df),
        ("reviews", reviews_df),
    ])

    # 7) Save anonymized versions back to disk
    prs_df.to_csv(prs_path, index=False)
    commits_df.to_csv(commits_path, index=False)
    reviews_df.to_csv(reviews_path, index=False)
