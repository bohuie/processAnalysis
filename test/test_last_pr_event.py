import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# -----------------------------
# Config
# -----------------------------
CLEAN_PREFIX = "CLEAN_pr_labels_"
TEAM_RE = re.compile(r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE)

# If you're 100% sure it's ONLY "self_merge", remove "self_merged".
MERGE_STATES = {"self_merge", "self_merged", "no_merge", "reviewed_merge"}


# -----------------------------
# Helpers
# -----------------------------
def find_project_root(start: Path) -> Path:
    """
    Walk upward until we find <root>/data/csv.
    Makes the test robust regardless of where pytest is launched from.
    """
    p = start.resolve()
    for _ in range(8):
        if (p / "data" / "csv").exists():
            return p
        p = p.parent
    raise RuntimeError(
        f"Could not locate project root containing data/csv starting from: {start}"
    )


def discover_clean_team_files(root: Path) -> list[Path]:
    data_folder = root / "data" / "csv"
    files = sorted(set(data_folder.glob(f"{CLEAN_PREFIX}year-long-project-team-*.csv")))
    if not files:
        raise FileNotFoundError(
            f"No CLEAN PR label CSVs found. Expected something like:\n"
            f"  {(data_folder / 'CLEAN_pr_labels_year-long-project-team-7.csv')}"
        )
    return files


def parse_team_name_and_number(fp: Path) -> tuple[str, str]:
    base = fp.name
    m = TEAM_RE.match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def normalize_event_field(event) -> list[str]:
    """
    Parse list-like strings into list; otherwise wrap scalar as single-item list.
    Mirrors old graphing.py behavior (list cells become multiple events).
    """
    if pd.isna(event):
        return []
    if isinstance(event, list):
        return [str(x).strip() for x in event if str(x).strip()]

    s = str(event).strip()
    if not s:
        return []

    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [str(parsed).strip()]
        except Exception:
            # if parsing fails, treat the raw string as one event
            return [s]

    return [s]


def load_and_flatten(fp: Path) -> pd.DataFrame:
    """
    Loads CLEAN file and returns flat rows:
      pr_id, timestamp, event
    with list-events exploded into separate events (stable ordering preserved).
    """
    df = pd.read_csv(fp, low_memory=False)

    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    # stable ordering inside identical timestamps (original row order)
    df["_row_idx"] = np.arange(len(df), dtype=np.int64)

    # explode list-like event cells while preserving the order inside the list
    df["event_list"] = df["event"].apply(normalize_event_field)
    df["event_pos"] = df["event_list"].apply(lambda xs: list(range(len(xs))))
    df = df.explode(["event_list", "event_pos"], ignore_index=True)

    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]

    df = df.sort_values(["pr_id", "timestamp", "_row_idx", "event_pos"]).reset_index(drop=True)

    return df[["pr_id", "timestamp", "event"]]


def compute_bad_last_events(files: list[Path]) -> pd.DataFrame:
    """
    Returns a dataframe of PRs whose last chronological event is NOT a merge state.
    Columns: team_name, team_number, pr_id, last_timestamp, last_event
    """
    bad_rows = []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp)
        flat = load_and_flatten(fp)
        if flat.empty:
            continue

        last_rows = flat.groupby("pr_id", as_index=False).tail(1).copy()
        last_rows["team_name"] = team_name
        last_rows["team_number"] = team_number
        last_rows.rename(columns={"event": "last_event", "timestamp": "last_timestamp"}, inplace=True)

        bad = last_rows[~last_rows["last_event"].isin(MERGE_STATES)].copy()
        if not bad.empty:
            bad_rows.append(bad[["team_name", "team_number", "pr_id", "last_timestamp", "last_event"]])

    if not bad_rows:
        return pd.DataFrame(columns=["team_name", "team_number", "pr_id", "last_timestamp", "last_event"])

    return pd.concat(bad_rows, ignore_index=True)


# -----------------------------
# The test
# -----------------------------
def test_last_state_per_pr_is_merge_state():
    root = find_project_root(Path(__file__).parent)
    files = discover_clean_team_files(root)

    bad = compute_bad_last_events(files)

    if bad.empty:
        # passes
        return

    # Helpful failure message: top bad last events + sample rows
    top_bad = bad["last_event"].value_counts().head(15).to_string()
    sample = bad.sort_values(["team_number", "pr_id"]).head(50).to_string(index=False)

    pytest.fail(
        "\nSome PR sessions do NOT end in a merge state before END.\n"
        f"Expected merge states: {sorted(MERGE_STATES)}\n\n"
        f"Bad PR count: {len(bad)}\n\n"
        f"Most common bad last_event values:\n{top_bad}\n\n"
        f"Sample bad rows (first 50):\n{sample}\n"
    )
