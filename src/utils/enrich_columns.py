from pathlib import Path
from typing import Union

import pandas as pd
import numpy as np


def _filter_by_valid_pr_ids(
    commits_df: pd.DataFrame,
    prs_df: pd.DataFrame,
    review_comments_df: pd.DataFrame | None = None,
):
    """Keep only PRs/comments whose pr_id appears in commits_df."""
    for name, df in [("commits", commits_df), ("prs", prs_df)]:
        if "pr_id" not in df.columns:
            raise KeyError(f"[ERROR] '{name}' file is missing required column 'pr_id'.")

    valid_pr_ids = set(commits_df["pr_id"].dropna().unique())

    prs_before = len(prs_df)
    prs_df = prs_df[prs_df["pr_id"].isin(valid_pr_ids)]
    print(f"[INFO] Filtered PRs: {prs_before} → {len(prs_df)}")

    if review_comments_df is not None:
        if "pr_id" not in review_comments_df.columns:
            raise KeyError("[ERROR] 'comments' file is missing required column 'pr_id'.")
        review_before = len(review_comments_df)
        review_comments_df = review_comments_df[review_comments_df["pr_id"].isin(valid_pr_ids)]
        print(f"[INFO] Filtered review comments: {review_before} → {len(review_comments_df)}")

    return prs_df, review_comments_df


def _compute_top_file_for_group(group: pd.DataFrame) -> pd.Series:
    """Helper used by add_top_file_metrics: compute top_file + % for a single PR."""
    file_sums = group.groupby("file_path")[["lines_added", "lines_deleted"]].sum()
    file_sums["total_change"] = file_sums["lines_added"] + file_sums["lines_deleted"]

    if file_sums.empty:
        return pd.Series({"top_file": None, "top_file_change_%": None})

    top_file_row = file_sums.sort_values("total_change", ascending=False).iloc[0]
    top_file = top_file_row.name
    top_file_total_change = top_file_row["total_change"]
    total_pr_change = file_sums["total_change"].sum()

    top_file_change_pct = (
        round((top_file_total_change / total_pr_change) * 100, 2)
        if total_pr_change > 0
        else None
    )

    return pd.Series(
        {
            "top_file": top_file,
            "top_file_change_%": top_file_change_pct,
        }
    )


def _compute_docs_updated_for_group(group: pd.DataFrame) -> bool:
    """Helper used by add_docs_updated_flag: any docs/readme in this PR?"""
    file_paths = group["file_path"].astype(str)
    return any(
        "docs" in fp.lower() or "readme" in fp.lower()
        for fp in file_paths
    )


# --- public utilities -------------------------------------------------

def add_top_file_metrics(team_folder: Union[Path, str]) -> None:
    """
    Add 'top_file' and 'top_file_change_%' columns to *_all_pull_requests.csv.

    - Loads *_PR_commits.csv and *_all_pull_requests.csv from team_folder
    - Normalizes PR timestamps
    - Filters PRs to only those with commits
    - Computes top file + % change per PR
    - Overwrites the PR CSV
    """
    team_folder = Path(team_folder)
    team_name = team_folder.name
    print(f"\n{'=' * 70}")
    print(f"[INFO] add_top_file_metrics for: {team_name}")
    print(f"{'=' * 70}")

    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if f.name.endswith("_PR_commits.csv")), None)
    prs_path = next((f for f in all_csvs if f.name.endswith("_all_pull_requests.csv")), None)

    if not all([commits_path, prs_path]):
        print(f"[WARN] Missing commits or PR CSV for {team_name}, skipping top_file enrichment.")
        return

    print("[INFO] Loading commits and PRs...")
    commits_df = pd.read_csv(commits_path)
    prs_df = pd.read_csv(prs_path)
    print(f"[INFO] Commits loaded: {len(commits_df)}, PRs loaded: {len(prs_df)}")

    prs_df, _ = _filter_by_valid_pr_ids(commits_df, prs_df, None)

    # Drop existing enrichment cols for idempotency
    for col in ["top_file", "top_file_change_%"]:
        if col in prs_df.columns:
            print(f"[INFO] Dropping existing enrichment column: {col}")
            prs_df = prs_df.drop(columns=[col])

    print("[INFO] Calculating top file metrics per PR...")
    top_file_info = (
        commits_df
        .groupby("pr_id", group_keys=False)
        .apply(_compute_top_file_for_group)
        .reset_index()
    )

    enriched_prs = prs_df.merge(top_file_info, on="pr_id", how="left")

    enriched_prs.to_csv(prs_path, index=False)
    print(f"[SUCCESS] Updated PRs with top_file metrics saved to: {prs_path}")
    print(f"[INFO] Final PR count: {len(enriched_prs)}")


def add_docs_updated_flag(team_folder: Union[Path, str]) -> None:
    """
    Add 'docs_updated' column to *_all_pull_requests.csv.

    - Loads *_PR_commits.csv and *_all_pull_requests.csv from team_folder
    - Filters PRs to only those with commits (same logic as original)
    - Sets docs_updated=True if any file_path under that PR looks like docs/readme
    - Overwrites the PR CSV
    """
    team_folder = Path(team_folder)
    team_name = team_folder.name
    print(f"\n{'=' * 70}")
    print(f"[INFO] add_docs_updated_flag for: {team_name}")
    print(f"{'=' * 70}")

    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if f.name.endswith("_PR_commits.csv")), None)
    prs_path = next((f for f in all_csvs if f.name.endswith("_all_pull_requests.csv")), None)

    if not all([commits_path, prs_path]):
        print(f"[WARN] Missing commits or PR CSV for {team_name}, skipping docs_updated enrichment.")
        return

    print("[INFO] Loading commits and PRs...")
    commits_df = pd.read_csv(commits_path)
    prs_df = pd.read_csv(prs_path)
    print(f"[INFO] Commits loaded: {len(commits_df)}, PRs loaded: {len(prs_df)}")

    prs_df, _ = _filter_by_valid_pr_ids(commits_df, prs_df, None)

    # Compute docs_updated per PR
    if "file_path" not in commits_df.columns:
        print("[WARN] 'file_path' column missing in commits; cannot compute docs_updated.")
        return

    print("[INFO] Calculating docs_updated flag per PR...")
    docs_df = (
        commits_df.groupby("pr_id")
        .apply(_compute_docs_updated_for_group)
        .reset_index()
        .rename(columns={0: "docs_updated"})
    )

    # Drop any old docs_updated column
    if "docs_updated" in prs_df.columns:
        print("[INFO] Dropping existing docs_updated column")
        prs_df = prs_df.drop(columns=["docs_updated"])

    enriched_prs = prs_df.merge(docs_df, on="pr_id", how="left")

    enriched_prs.to_csv(prs_path, index=False)
    print(f"[SUCCESS] Updated PRs with docs_updated flag saved to: {prs_path}")
    print(f"[INFO] Final PR count: {len(enriched_prs)}")



def add_order_of_review(team_folder: Union[Path, str]) -> None:
    """
    Add 'order_of_review' to *_review-comments.csv.

    NEW LOGIC (reviewer-based):
    - Loads *_PR_commits.csv and *_review-comments.csv from team_folder
    - Filters comments to only PRs that appear in commits
    - For each PR:
        * Sort comments by created_at
        * Determine the order of distinct reviewers (using 'author' column):
              1st unique reviewer  -> 'first'
              2nd unique reviewer  -> 'second'
              3rd+ unique reviewers -> 'additional'
        * All comments from the same reviewer on that PR get the same tag
    - Overwrites the review-comments CSV
    """
    team_folder = Path(team_folder)
    team_name = team_folder.name
    print(f"\n{'=' * 70}")
    print(f"[INFO] add_order_of_review for: {team_name}")
    print(f"{'=' * 70}")

    all_csvs = list(team_folder.glob("*.csv"))
    commits_path = next((f for f in all_csvs if f.name.endswith("_PR_commits.csv")), None)
    review_comments_path = next((f for f in all_csvs if f.name.endswith("_review-comments.csv")), None)

    if not all([commits_path, review_comments_path]):
        print(f"[WARN] Missing commits or review-comments CSV for {team_name}, skipping order_of_review.")
        return

    print("[INFO] Loading commits and review comments...")
    commits_df = pd.read_csv(commits_path)
    review_comments_df = pd.read_csv(review_comments_path)
    print(f"[INFO] Commits loaded: {len(commits_df)}, Comments loaded: {len(review_comments_df)}")

    # Filter comments to PRs that have commits
    _, review_comments_df = _filter_by_valid_pr_ids(
        commits_df,
        pd.DataFrame({"pr_id": commits_df["pr_id"].dropna().unique()}),
        review_comments_df,
    )

    if review_comments_df.empty:
        print("[INFO] No review comments left after filtering; nothing to label.")
        review_comments_df.to_csv(review_comments_path, index=False)
        print(f"[SUCCESS] Saved (possibly empty) review-comments file: {review_comments_path}")
        return

    if "created_at" not in review_comments_df.columns:
        raise KeyError("[ERROR] review-comments.csv is missing 'created_at' column.")
    if "author" not in review_comments_df.columns:
        raise KeyError("[ERROR] review-comments.csv is missing 'author' column for reviewer usernames.")

    print("[INFO] Calculating reviewer-based order_of_review for review comments...")
    review_comments_df["created_at"] = pd.to_datetime(review_comments_df["created_at"], errors="coerce")

    # Sort globally so within each PR group, time order is respected
    review_comments_df = review_comments_df.sort_values(["pr_id", "created_at"])

    review_comments_df = (
        review_comments_df
        .groupby("pr_id", group_keys=False)
        .apply(_assign_order_for_pr)
    )

    review_comments_df.to_csv(review_comments_path, index=False)
    print(f"[SUCCESS] Updated review comments with reviewer-based order_of_review saved to: {review_comments_path}")
    print(f"[INFO] Final comments count: {len(review_comments_df)}")
    
    
    
def _assign_order_for_pr(group: pd.DataFrame) -> pd.DataFrame:
    """
    For a single PR:
    - Determine unique reviewers (author) in chronological order.
    - Map first reviewer -> 'first', second -> 'second', rest -> 'additional'.
    - Assign that label to all comments of that reviewer on this PR.
    """
    # Normalize author strings
    authors = group["author"].astype(str).fillna("").str.strip()

    # Unique reviewers in order of appearance
    unique_reviewers = []
    for a in authors:
        if a and a not in unique_reviewers:
            unique_reviewers.append(a)

    # Build mapping reviewer -> tag
    reviewer_to_tag = {}
    for idx, reviewer in enumerate(unique_reviewers):
        if idx == 0:
            reviewer_to_tag[reviewer] = "first"
        elif idx == 1:
            reviewer_to_tag[reviewer] = "second"
        else:
            reviewer_to_tag[reviewer] = "additional"

    group["order_of_review"] = authors.apply(
        lambda a: reviewer_to_tag.get(a, None) if a else None
    )
    return group
