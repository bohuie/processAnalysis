import os
from typing import Tuple
import pandas as pd

from src.utils.anonymize_columns import anonymize_author_columns
from src.utils.logFilter import find_log_pr_ids, drop_pr_ids

from event_labelling.Communication.helpers_comm import drop_bots_in_author_like_columns


def _clean_path(original_path: str) -> str:
    folder = os.path.dirname(original_path)
    base = os.path.basename(original_path)
    return os.path.join(folder, f"CLEAN_{base}")


def preprocess_team_csvs(
    team_name: str,
    team_folder: str,
    prs_path: str,
    commits_path: str,
) -> Tuple[str, str]:
    """
    Communication preprocessing:
      - drop bots (PRs + commits)
      - detect "log-ish" PR_ids across BOTH sources and drop everywhere
      - write CLEAN_*.csv (do not overwrite originals)
      - anonymize author columns on CLEAN files
    """
    print("[STEP -1A] Loading raw CSVs for preprocessing...")
    raw_prs_df = pd.read_csv(prs_path)
    raw_commits_df = pd.read_csv(commits_path)

    # 1) Remove bots
    raw_prs_df = drop_bots_in_author_like_columns(raw_prs_df, f"{team_name} PRs")
    raw_commits_df = drop_bots_in_author_like_columns(raw_commits_df, f"{team_name} Commits")

    # 2) Detect log-ish PRs across BOTH sources, then drop everywhere
    bad_pr_ids = set()
    bad_pr_ids |= find_log_pr_ids(raw_prs_df, f"{team_name} PRs")
    bad_pr_ids |= find_log_pr_ids(raw_commits_df, f"{team_name} Commits")
    print(f"[STEP -1B MASTER] {team_name}: total unique log PR_ids across PRs+Commits = {len(bad_pr_ids)}")

    raw_prs_df = drop_pr_ids(raw_prs_df, bad_pr_ids, f"{team_name} PRs")
    raw_commits_df = drop_pr_ids(raw_commits_df, bad_pr_ids, f"{team_name} Commits")

    # 3) Write CLEAN files (NOT overwriting originals)
    clean_prs_path = _clean_path(prs_path)
    clean_commits_path = _clean_path(commits_path)

    raw_prs_df.to_csv(clean_prs_path, index=False)
    raw_commits_df.to_csv(clean_commits_path, index=False)

    # 4) Anonymize author columns on CLEAN files
    print("[STEP -1C] Anonymizing author columns on CLEAN CSVs...")
    prs_df = pd.read_csv(clean_prs_path)
    commits_df = pd.read_csv(clean_commits_path)

    anonymize_author_columns(
        [
            ("prs", prs_df),
            ("commits", commits_df),
        ]
    )

    prs_df.to_csv(clean_prs_path, index=False)
    commits_df.to_csv(clean_commits_path, index=False)

    return clean_prs_path, clean_commits_path