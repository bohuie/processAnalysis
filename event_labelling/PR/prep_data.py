import os
from typing import Tuple
import pandas as pd
from src.utils.anonymize_columns import (
    anonymize_author_columns,)
from src.utils.enrich_columns import add_order_of_review

# helper imports
from event_labelling.PR.helpers_pr import (
    drop_bots_in_author_like_columns,
    find_log_pr_ids,
    drop_pr_ids,
)


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


def _clean_path(original_path: str) -> str:
    """
    Turn /path/to/foo.csv into /path/to/CLEAN_foo.csv
    """
    folder = os.path.dirname(original_path)
    base = os.path.basename(original_path)
    return os.path.join(folder, f"CLEAN_{base}")


def preprocess_team_csvs(
    team_folder: str,
    team_name: str,
    prs_path: str,
    commits_path: str,
    reviews_path: str,
) -> Tuple[str, str, str]:
    """
    Preprocess originals but DO NOT overwrite them.
    Write CLEAN_*.csv files and return their paths.
    """
    print("[STEP -1A] Loading raw CSVs for preprocessing...")
    raw_prs_df = pd.read_csv(prs_path)
    raw_commits_df = pd.read_csv(commits_path)
    raw_reviews_df = pd.read_csv(reviews_path)

    # 1) Remove bots
    raw_prs_df = drop_bots_in_author_like_columns(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_bots_in_author_like_columns(raw_commits_df, f"{team_name} Commits")
    raw_reviews_df = drop_bots_in_author_like_columns(raw_reviews_df, f"{team_name} Reviews")

    # 2) Detect log-ish PRs across ALL sources, then drop everywhere
    bad_pr_ids = set()
    bad_pr_ids |= find_log_pr_ids(raw_prs_df, f"{team_name} PRs")
    bad_pr_ids |= find_log_pr_ids(raw_commits_df, f"{team_name} Commits")
    bad_pr_ids |= find_log_pr_ids(raw_reviews_df, f"{team_name} Reviews")

    print(f"[STEP -1B MASTER] {team_name}: total unique log PR_ids across ALL CSVs = {len(bad_pr_ids)}")

    raw_prs_df = drop_pr_ids(raw_prs_df, bad_pr_ids, f"{team_name} PRs")
    raw_commits_df = drop_pr_ids(raw_commits_df, bad_pr_ids, f"{team_name} Commits")
    raw_reviews_df = drop_pr_ids(raw_reviews_df, bad_pr_ids, f"{team_name} Reviews")

    # 3) Review-specific filters
    raw_reviews_df = _apply_review_specific_filters(raw_reviews_df, team_name)

    # 4) Write CLEAN files (NOT overwriting originals)
    clean_prs_path = _clean_path(prs_path)
    clean_commits_path = _clean_path(commits_path)
    clean_reviews_path = _clean_path(reviews_path)

    raw_prs_df.to_csv(clean_prs_path, index=False)
    raw_commits_df.to_csv(clean_commits_path, index=False)
    raw_reviews_df.to_csv(clean_reviews_path, index=False)

    # 5) Add order_of_review to the CLEAN review-comments
    print("[STEP -1F] Adding order_of_review to CLEAN review-comments...")
    add_order_of_review(team_folder)

    # 6) Reload CLEAN CSVs (now containing order_of_review)
    print("[STEP -1G] Anonymizing author columns on CLEAN CSVs...")
    prs_df = pd.read_csv(clean_prs_path)
    commits_df = pd.read_csv(clean_commits_path)
    reviews_df = pd.read_csv(clean_reviews_path)

    anonymize_author_columns([
        ("prs", prs_df),
        ("commits", commits_df),
        ("reviews", reviews_df),
    ])

    prs_df.to_csv(clean_prs_path, index=False)
    commits_df.to_csv(clean_commits_path, index=False)
    reviews_df.to_csv(clean_reviews_path, index=False)

    return clean_prs_path, clean_commits_path, clean_reviews_path
