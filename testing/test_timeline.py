# test if all merge states' relevant timestamps are the very last timestamp in the pr timeline
# test if all the review states' timestamps are after pr states' timestamps

import os
import pandas as pd
import pytest
import re
import ast
import csv

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
def clean_event(ev):
    """
    Extract event name(s) from serialized list strings like ['event_name'].
    Safely handles malformed strings and multi-event lists.
    """
    if isinstance(ev, str):
        ev = ev.strip()
        try:
            parsed = ast.literal_eval(ev)
            if isinstance(parsed, list) and len(parsed) == 1:
                return parsed[0]
            elif isinstance(parsed, list):
                return [str(x) for x in parsed]
            else:
                return str(parsed)
        except Exception:
            # fallback cleanup for odd formatting
            return ev.strip("[]").strip("'").strip('"')
    return ev


def to_datetime_utc(series):
    """
    Convert mixed-format timestamps (Z, +0000, -07:00, -0800) into UTC datetimes.
    Ensures consistent parsing regardless of timezone format.
    """
    s = series.astype(str).str.strip()
    # Normalize timezone format to always include colon (e.g., +0000 → +00:00)
    s = s.str.replace(r"([+-]\d{2})(\d{2})$", r"\1:\2", regex=True)
    # Add 'T' separator if missing
    s = s.str.replace(r"(?<=\d{2}) (?=\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})", "T", regex=True)
    # Convert to UTC datetime
    return pd.to_datetime(s, utc=True, errors="coerce")


def get_label_fp(team_number):
    return os.path.join(DATA_DIR, f"pr_labels_year-long-project-team-{team_number}.csv")


# test if merge states are the last timestamps chronologically
@pytest.mark.parametrize("team_number", ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22"])
def test_merge_timestamps_are_last(team_number):
    fp = get_label_fp(team_number)
    df = pd.read_csv(fp)
    df["event"] = df["event"].apply(clean_event)

    df["created_at_dt"] = to_datetime_utc(df.get("created_at", pd.Series(dtype=str)))
    df["merged_at_dt"] = to_datetime_utc(df.get("merged_at", pd.Series(dtype=str)))
    df["updated_at_dt"] = to_datetime_utc(df.get("updated_at", pd.Series(dtype=str)))

    bad_prs = {}

    for pr_id, g in df.groupby("pr_id"):
        timeline = []

        for _, row in g.iterrows():
            ev = row["event"]
            if isinstance(ev, list):
                # skip multi-event rows, they aren't expected in label CSV
                continue

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

        # The final timestamp(s)
        last_ts = timeline[-1][0]
        last_events = [ev for ts, ev in timeline if ts == last_ts]

        # If last event is not a merge, mark as bad
        if not any(ev in MERGE_STATES_REVIEWED.union(MERGE_STATE_NO_MERGE) for ev in last_events):
            bad_prs[pr_id] = timeline

    if bad_prs:
        total_prs = df["pr_id"].nunique()
        out_path = os.path.join(DATA_DIR, f"team-{team_number}_merge_not_last.csv")

        # Build a compact DataFrame with violating rows only
        rows = []
        for pid, timeline in bad_prs.items():
            for ts, ev in timeline:
                rows.append({"pr_id": pid, "timestamp": ts, "event": ev})

        pd.DataFrame(rows).to_csv(out_path, index=False)

        pytest.fail(
            f"{len(bad_prs)} PRs (out of {total_prs}) have merge timestamps not last for Team {team_number}.\n"
            f"→ Violating rows exported to: {out_path}"
        )



# test that review states occur after pr states' timestamps
@pytest.mark.parametrize("team_number", ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22"])
def test_review_after_pr_states(team_number):
    fp = get_label_fp(team_number)
    df = pd.read_csv(fp)
    df["event"] = df["event"].apply(clean_event)

    df["created_at_dt"] = to_datetime_utc(df.get("created_at", pd.Series(dtype=str)))

    violations = {}

    for pr_id, g in df.groupby("pr_id"):
        # subset PR + Review states
        subset = g[g["event"].isin(PR_STATES.union(REVIEW_STATES))].copy()
        if subset.empty:
            continue

        subset = subset.dropna(subset=["created_at_dt"]).sort_values("created_at_dt")

        # If a review appears before any PR description → violation
        seen_pr = False
        violation_found = False
        for _, row in subset.iterrows():
            ev = row["event"]
            if ev in PR_STATES:
                seen_pr = True
            elif ev in REVIEW_STATES and not seen_pr:
                violation_found = True
                break

        # If earliest review < latest PR timestamp → violation
        if not violation_found:
            last_pr_ts = subset.loc[subset["event"].isin(PR_STATES), "created_at_dt"].max()
            first_review_ts = subset.loc[subset["event"].isin(REVIEW_STATES), "created_at_dt"].min()
            if pd.notna(last_pr_ts) and pd.notna(first_review_ts) and first_review_ts < last_pr_ts:
                violation_found = True

        if violation_found:
            violations[pr_id] = subset[["created_at_dt", "event"]]

    if violations:
        total_prs = df["pr_id"].nunique()
        out_path = os.path.join(DATA_DIR, f"team-{team_number}_review_before_pr.csv")

        # Collect only violating rows
        rows = []
        for pid, timeline in violations.items():
            for _, r in timeline.iterrows():
                rows.append({
                    "pr_id": pid,
                    "timestamp": r["created_at_dt"],
                    "event": r["event"]
                })

        pd.DataFrame(rows).to_csv(out_path, index=False)

        pytest.fail(
            f"{len(violations)} PRs (out of {total_prs}) have review timestamps before PR states for Team {team_number}.\n"
            f"→ Violating rows exported to: {out_path}"
        )
