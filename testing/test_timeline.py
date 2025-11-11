# test if all merge states' relevant timestamps are the very last timestamp in the pr timeline
# test if all the review states' timestamps are after pr states' timestamps

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
def to_datetime_utc(series):
    """Convert timestamps to timezone-aware UTC datetimes."""
    s = series.astype(str).str.strip()
    s = s.str.replace(r"(?<=\d{2}) (?=\d{2}:\d{2}:\d{2}[-+]\d{2}:\d{2})", "T", regex=True)
    return pd.to_datetime(s, utc=True, errors="coerce")

def get_label_fp(team_number):
    return os.path.join(DATA_DIR, f"pr_labels_year-long-project-team-{team_number}.csv")

# test if merge states are the last timestamps chronologically
@pytest.mark.parametrize("team_number", ["20", "14"])  # add others as needed
def test_merge_timestamps_are_last(team_number):
    fp = get_label_fp(team_number)
    df = pd.read_csv(fp)

    df["created_at_dt"] = to_datetime_utc(df.get("created_at", pd.Series(dtype=str)))
    df["merged_at_dt"] = to_datetime_utc(df.get("merged_at", pd.Series(dtype=str)))
    df["updated_at_dt"] = to_datetime_utc(df.get("updated_at", pd.Series(dtype=str)))

    bad_prs = {}

    for pr_id, g in df.groupby("pr_id"):
        timeline = []

        for _, row in g.iterrows():
            ev = str(row["event"]).strip()
            if ev in PR_STATES or ev in REVIEW_STATES:
                ts = row["created_at_dt"]
            elif ev in MERGE_STATES_REVIEWED:
                ts = row["merged_at_dt"]
            elif ev in MERGE_STATE_NO_MERGE:
                ts = row["updated_at_dt"]
            else:
                continue
            if pd.notna(ts):
                timeline.append((ts, ev))

        if not timeline:
            continue

        timeline.sort(key=lambda x: x[0])
        last_ts = timeline[-1][0]
        last_events = [ev for ts, ev in timeline if ts == last_ts]

        # If the last timestamp is not a merge state, record it
        if not any(ev in MERGE_STATES_REVIEWED or ev in MERGE_STATE_NO_MERGE for ev in last_events):
            bad_prs[pr_id] = timeline

    if bad_prs:
        msg = [f"{len(bad_prs)} PRs have merge timestamps not last for Team {team_number}:"]
        for pid, timeline in bad_prs.items():
            msg.append(f"\n  PR {pid} timeline:")
            for ts, ev in timeline:
                msg.append(f"    {ts} — {ev}")
        pytest.fail("\n".join(msg))

# test that review states occur after pr states' timestamps
@pytest.mark.parametrize("team_number", ["14"])
def test_review_after_pr_states(team_number):
    fp = get_label_fp(team_number)
    df = pd.read_csv(fp)

    df["created_at_dt"] = to_datetime_utc(df.get("created_at", pd.Series(dtype=str)))

    violations = {}

    for pr_id, g in df.groupby("pr_id"):
        pr_times = g.loc[g["event"].isin(PR_STATES), "created_at_dt"].dropna()
        review_times = g.loc[g["event"].isin(REVIEW_STATES), "created_at_dt"].dropna()

        if pr_times.empty or review_times.empty:
            continue

        latest_pr = pr_times.max()
        earliest_review = review_times.min()

        if earliest_review < latest_pr:
            timeline = g.loc[g["event"].isin(PR_STATES.union(REVIEW_STATES)), ["event", "created_at_dt"]]
            timeline = timeline.sort_values("created_at_dt")
            violations[pr_id] = timeline

    if violations:
        msg = [f"{len(violations)} PRs have review timestamps before PR states for Team {team_number}:"]
        for pid, timeline in violations.items():
            msg.append(f"\n  PR {pid} PR/Review timeline:")
            for _, r in timeline.iterrows():
                msg.append(f"    {r['created_at_dt']} — {r['event']}")
        pytest.fail("\n".join(msg))
