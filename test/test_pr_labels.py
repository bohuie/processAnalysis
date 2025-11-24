# test if created_at of all pr states are same as pr.csv
# test if created_at of all review states are same as review-comments.csv
# test if all merged_at of reviewed_merge and self_merged are same as pr.csv
# test if all updated_at of no_merge are the same as pr.csv

import os
import pandas as pd
import pytest
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data", "csv")

PR_STATES = {"pr_description_unclear", "pr_description_clear"}
REVIEW_STATES = {
    "non_constructive_first_review", "non_constructive_second_review", "non_constructive_additional_review",
    "constructive_first_review", "constructive_second_review", "constructive_additional_review"
}
MERGE_STATES_REVIEWED = {"self_merged", "reviewed_merge"}
MERGE_STATE_NO_MERGE = {"no_merge"}

# helpers
def to_utc(series):
    """Convert mixed-format timestamps (Z, -07:00, -08:00) to uniform UTC (+00:00)."""
    s = series.astype(str).str.strip()
    # Fix missing 'T' before timezone offsets
    s = s.str.replace(r"(?<=\d{2}) (?=\d{2}:\d{2}:\d{2}[-+]\d{2}:\d{2})", "T", regex=True)
    dt = pd.to_datetime(s, utc=True, errors="coerce")
    return dt.dt.strftime("%Y-%m-%d %H:%M:%S%z")


def parse_team_number(label_fp):
    """Extract team number from the label CSV filename."""
    match = re.search(r"team-(\d+)", os.path.basename(label_fp))
    return match.group(1) if match else "unknown"


def get_team_filepaths(team_number):
    """Return paths for label, PR, and review CSVs for a given team number."""
    label_fp = os.path.join(DATA_DIR, f"pr_labels_year-long-project-team-{team_number}.csv")
    team_dir = os.path.join(DATA_DIR, f"year-long-project-team-{team_number}")
    pr_fp = os.path.join(team_dir, f"year-long-project-team-{team_number}_all_pull_requests.csv")
    review_fp = os.path.join(team_dir, f"year-long-project-team-{team_number}_review-comments.csv")
    return label_fp, pr_fp, review_fp


def compare_timestamps(label_ts, src_ts):
    """Return True if timestamps match (string comparison after strip)."""
    return str(label_ts).strip() == str(src_ts).strip()


# test
@pytest.mark.parametrize("team_number", ["14"])  # Add more like ["13", "14", "15"] if needed
def test_label_vs_source_timestamps(team_number):
    """Validate that timestamps in label CSV match the corresponding source CSVs."""

    label_fp, pr_fp, review_fp = get_team_filepaths(team_number)

    # Load all three CSVs
    df_label = pd.read_csv(label_fp)
    df_pr = pd.read_csv(pr_fp)
    df_review = pd.read_csv(review_fp)

    # Convert source timestamps to UTC for fair comparison
    for col in ["created_at", "merged_at", "updated_at"]:
        if col in df_pr.columns:
            df_pr[col] = to_utc(df_pr[col])
    if "created_at" in df_review.columns:
        df_review["created_at"] = to_utc(df_review["created_at"])

    mismatches = []

    for i, row in df_label.iterrows():
        event = str(row["event"]).strip()
        pr_id = row.get("pr_id")

        if not event or pd.isna(pr_id):
            continue

        # pr states
        if event in PR_STATES:
            src_ts = df_pr.loc[df_pr["pr_id"] == pr_id, "created_at"]
            if not src_ts.empty and not compare_timestamps(row["created_at"], src_ts.iloc[0]):
                mismatches.append(("PR_STATE", pr_id, event, row["created_at"], src_ts.iloc[0]))

        # review states
        elif event in REVIEW_STATES:
            pr_author = str(row.get("pr_author")).strip()
            comment = str(row.get("comment_body")).strip()
            cond = (
                (df_review["pr_id"] == pr_id) &
                (df_review["author"].astype(str).str.strip() == pr_author) &
                (df_review["comment_body"].astype(str).str.strip() == comment)
            )
            src_ts = df_review.loc[cond, "created_at"]
            if not src_ts.empty and not compare_timestamps(row["created_at"], src_ts.iloc[0]):
                mismatches.append(("REVIEW_STATE", pr_id, event, row["created_at"], src_ts.iloc[0]))

        # self_merged / reviewed_merge
        elif event in MERGE_STATES_REVIEWED:
            src_ts = df_pr.loc[df_pr["pr_id"] == pr_id, "merged_at"]
            if not src_ts.empty and not compare_timestamps(row["merged_at"], src_ts.iloc[0]):
                mismatches.append(("MERGE_STATE", pr_id, event, row["merged_at"], src_ts.iloc[0]))

        # no merge
        elif event in MERGE_STATE_NO_MERGE:
            src_ts = df_pr.loc[df_pr["pr_id"] == pr_id, "updated_at"]
            if not src_ts.empty and not compare_timestamps(row["updated_at"], src_ts.iloc[0]):
                mismatches.append(("NO_MERGE_STATE", pr_id, event, row["updated_at"], src_ts.iloc[0]))

    # If mismatches exist, fail the test with details
    if mismatches:
        msg_lines = [f"{len(mismatches)} mismatches found for Team {team_number}:"]
        for cat, pid, ev, label_ts, src_ts in mismatches:
            msg_lines.append(
                f"  • {cat} | PR {pid} | {ev}\n"
                f"    Label: {label_ts}\n"
                f"    Source: {src_ts}"
            )
        pytest.fail("\n" + "\n".join(msg_lines))
        


