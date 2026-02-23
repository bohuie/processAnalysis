"""
individual_metrics.py

Generates per-developer label-based metrics from event-label CSVs.

Each PR's events (labels like 'Meaningful Branch Name', 'self_merge', etc.)
are joined to the PR author via CLEAN_*_all_pull_requests.csv, then
aggregated per developer.

Metrics mirror the fields used in graphing.py (event frequencies and
Markov transition counts/probabilities) but scoped to individual developers
rather than the whole team.

Controlled by env vars (same as transition_edges.py / graphing.py):
  FOLDER_SOURCE = "branching" | "pr"
  FILE_SOURCE   = "branching" | "pr"   (selects label CSV source)
"""

import os
import re
import glob
import json
import ast
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT        = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

FOLDER_SOURCE = os.getenv("FOLDER_SOURCE", "branching")   # output subdir
FILE_SOURCE   = os.getenv("FILE_SOURCE",   "branching")   # label CSV source

# ── Label-CSV configs (mirrors transition_edges.py) ────────────────────────
CONFIGS = {
    "branching": {
        "data_folder": os.path.join(ROOT, "data", "graph_labels", "clean"),
        "prefix":      "CLEAN_year-long-project-team-",
        "pattern":     "*_labels_branching_and_structure.csv",
        "regex":       re.compile(
            r"^CLEAN_(year-long-project-team-\d+)_labels_branching_and_structure\.csv$",
            re.IGNORECASE,
        ),
    },
    "pr": {
        "data_folder": os.path.join(ROOT, "data", "csv"),
        "prefix":      "CLEAN_pr_labels_",
        "pattern":     "year-long-project-team-*.csv",
        "regex":       re.compile(
            r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$",
            re.IGNORECASE,
        ),
    },
}

OUTPUT_DIR = os.path.join(ROOT, "data", "outputs", FOLDER_SOURCE)


# ── Helpers ─────────────────────────────────────────────────────────────────

def normalize_username(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower().str.strip()


def normalize_event_field(event) -> list[str]:
    """Parse a single event cell into a list of label strings.
    Handles plain strings and stringified Python lists, e.g. \"['a','b']\".
    Mirrors transition_edges.py behaviour exactly.
    """
    if isinstance(event, list):
        return [str(x).strip() for x in event if str(x).strip()]
    if pd.isna(event):
        return []
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
            return [s]
    return [s]


def safe_rate(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0.0


# ── Core per-team processing ─────────────────────────────────────────────────

def load_label_csv(label_fp: str) -> pd.DataFrame:
    """Load a label CSV and explode list-valued event cells to one row per label."""
    df = pd.read_csv(label_fp, low_memory=False)
    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label_fp} missing columns: {missing}")

    df["pr_id"]    = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"]= pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["_row_idx"] = np.arange(len(df))

    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()
    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("") & df["event"].ne("nan")]
    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)
    return df[["pr_id", "timestamp", "event"]]


def load_pr_authors(team_dir: str, team_name: str) -> pd.DataFrame:
    """Load pr_id → pr_author mapping from the CLEAN PR CSV."""
    pr_file = os.path.join(team_dir, f"CLEAN_{team_name}_all_pull_requests.csv")
    if not os.path.exists(pr_file):
        print(f"[WARN] PR author file not found: {pr_file}")
        return pd.DataFrame(columns=["pr_id", "pr_author"])
    df = pd.read_csv(pr_file, usecols=["pr_id", "pr_author"], low_memory=False)
    df["pr_id"]     = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["pr_author"] = normalize_username(df["pr_author"])
    return df[["pr_id", "pr_author"]].drop_duplicates("pr_id")


def compute_dev_metrics(dev_events: pd.DataFrame) -> dict:
    """
    Given all label-events for a single developer, return a flat dict of metrics.

    dev_events columns: pr_id, timestamp, event
    """
    num_prs        = dev_events["pr_id"].nunique()
    total_labels   = len(dev_events)
    unique_labels  = dev_events["event"].nunique()

    # ── Label frequency ──────────────────────────────────────────────────────
    label_counts: dict[str, int] = dev_events["event"].value_counts().to_dict()
    top_label = dev_events["event"].value_counts().idxmax() if total_labels > 0 else ""

    # ── Per-label rates (count / num_prs, one row per PR counts once) ────────
    # Use PR-level: does the PR have ≥1 occurrence of this label?
    pr_labels = dev_events.groupby("pr_id")["event"].apply(set)

    def pr_rate(label: str) -> float:
        has = sum(1 for s in pr_labels if label in s)
        return safe_rate(has, num_prs)

    meaningful_branch_rate   = pr_rate("Meaningful Branch Name")
    random_branch_rate       = pr_rate("Random Branch Name")
    self_merge_rate          = pr_rate("self_merge")
    reviewed_merge_rate      = pr_rate("reviewed_merge")
    one_feature_rate         = pr_rate("one Features Per Branch")
    up_to_date_rate          = pr_rate("up-to-date")
    outdated_rate            = pr_rate("outdated")
    still_open_rate          = pr_rate("still_open")
    # PR-mode labels
    pr_description_clear_rate      = pr_rate("pr_description_clear")
    pr_description_unclear_rate    = pr_rate("pr_description_unclear")
    constructive_review_rate       = pr_rate("constructive_additional_review")
    approved_empty_review_rate     = pr_rate("approved_empty_review")
    changes_requested_rate         = pr_rate("changes_requested")

    # ── Transition stats (mirrors graphing.py edge computation) ─────────────
    # Per PR: consecutive event pairs after sorting by timestamp
    transition_counter: dict[tuple, int] = {}
    first_events: list[str] = []
    last_events:  list[str] = []
    total_transitions = 0

    for _, pr_grp in dev_events.groupby("pr_id"):
        events = pr_grp["event"].tolist()
        if not events:
            continue
        first_events.append(events[0])
        last_events.append(events[-1])
        for i in range(len(events) - 1):
            a, b = events[i], events[i + 1]
            transition_counter[(a, b)] = transition_counter.get((a, b), 0) + 1
            total_transitions += 1

    unique_transitions = len(transition_counter)
    avg_transitions_per_pr = round(total_transitions / num_prs, 3) if num_prs > 0 else 0.0

    # Top transition
    top_transition      = ""
    top_transition_prob = 0.0
    if transition_counter:
        top_pair  = max(transition_counter, key=transition_counter.get)
        top_count = transition_counter[top_pair]
        top_transition = f"{top_pair[0]} -> {top_pair[1]}"
        # Probability: count / total outgoing from the "from" node (for this dev)
        from_total = sum(
            c for (a, _), c in transition_counter.items() if a == top_pair[0]
        )
        top_transition_prob = round(top_count / from_total, 4) if from_total > 0 else 0.0

    most_common_first_event = (
        pd.Series(first_events).value_counts().idxmax() if first_events else ""
    )
    most_common_last_event = (
        pd.Series(last_events).value_counts().idxmax() if last_events else ""
    )

    return {
        "num_prs":                      num_prs,
        "total_labels":                 total_labels,
        "unique_labels":                unique_labels,
        "top_label":                    top_label,
        "label_counts_json":            json.dumps(label_counts),
        # ── Branching-mode rates ──
        "meaningful_branch_rate":       meaningful_branch_rate,
        "random_branch_rate":           random_branch_rate,
        "one_feature_per_branch_rate":  one_feature_rate,
        "self_merge_rate":              self_merge_rate,
        "reviewed_merge_rate":          reviewed_merge_rate,
        "up_to_date_rate":              up_to_date_rate,
        "outdated_rate":                outdated_rate,
        "still_open_rate":              still_open_rate,
        # ── PR-mode rates ──
        "pr_description_clear_rate":    pr_description_clear_rate,
        "pr_description_unclear_rate":  pr_description_unclear_rate,
        "constructive_review_rate":     constructive_review_rate,
        "approved_empty_review_rate":   approved_empty_review_rate,
        "changes_requested_rate":       changes_requested_rate,
        # ── Transition / sequence stats ──
        "total_transitions":            total_transitions,
        "unique_transitions":           unique_transitions,
        "avg_transitions_per_pr":       avg_transitions_per_pr,
        "top_transition":               top_transition,
        "top_transition_prob":          top_transition_prob,
        "most_common_first_label":      most_common_first_event,
        "most_common_last_label":       most_common_last_event,
    }


def process_team(label_fp: str, config: dict) -> pd.DataFrame:
    """Process one team's label CSV and return a per-developer metrics DataFrame."""
    base      = os.path.basename(label_fp)
    m         = config["regex"].match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m     = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"

    # Load event labels
    try:
        label_df = load_label_csv(label_fp)
    except Exception as e:
        print(f"[ERROR] Could not load {label_fp}: {e}")
        return pd.DataFrame()

    if label_df.empty:
        print(f"[WARN] No usable events in {label_fp}")
        return pd.DataFrame()

    # Load PR authors
    team_dir  = os.path.join(ROOT, "data", "csv", team_name)
    author_df = load_pr_authors(team_dir, team_name)

    if author_df.empty:
        print(f"[WARN] No author data for {team_name} — skipping")
        return pd.DataFrame()

    # Join events → authors
    merged = label_df.merge(author_df, on="pr_id", how="inner")
    if merged.empty:
        print(f"[WARN] No pr_id overlap between labels and PR author data for {team_name}")
        return pd.DataFrame()

    # Compute per-developer metrics
    rows = []
    for dev, dev_grp in merged.groupby("pr_author"):
        if not dev:
            continue
        metrics = compute_dev_metrics(dev_grp[["pr_id", "timestamp", "event"]])
        rows.append({"team_number": team_number, "developer": dev, **metrics})

    return pd.DataFrame(rows)


def main():
    config = CONFIGS.get(FILE_SOURCE)
    if config is None:
        raise ValueError(
            f"Invalid FILE_SOURCE: '{FILE_SOURCE}'. Must be 'branching' or 'pr'."
        )

    data_folder    = config["data_folder"]
    search_pattern = os.path.join(data_folder, f"{config['prefix']}{config['pattern']}")
    label_files    = sorted(glob.glob(search_pattern))

    print(f"[INFO] FILE_SOURCE   : {FILE_SOURCE}")
    print(f"[INFO] FOLDER_SOURCE : {FOLDER_SOURCE}")
    print(f"[INFO] Label files   : {data_folder}")
    print(f"[INFO] Output dir    : {OUTPUT_DIR}")
    print(f"[INFO] Found {len(label_files)} label file(s).")

    if not label_files:
        print("[WARN] No label files found. Check FILE_SOURCE and data directories.")
        return

    all_metrics = []
    for fp in label_files:
        print(f"  Processing {os.path.basename(fp)} ...")
        df = process_team(fp, config)
        if not df.empty:
            all_metrics.append(df)

    if not all_metrics:
        print("[WARN] No metrics generated.")
        return

    final_df = pd.concat(all_metrics, ignore_index=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "individual_metrics.csv")
    final_df.to_csv(output_path, index=False)

    print(
        f"\n[SUCCESS] Generated metrics for {len(final_df)} developers "
        f"across {final_df['team_number'].nunique()} team(s)."
    )
    print(f"Output: {output_path}")
    print("\nColumns:", final_df.columns.tolist())
    print("\nPreview:")
    print(final_df.head().to_string())


if __name__ == "__main__":
    main()
