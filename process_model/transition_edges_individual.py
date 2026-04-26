from __future__ import annotations

import os
import re
import glob
import numpy as np
import pandas as pd

from src.utils.markov_common import (
    normalize_event_field,
    explode_and_sort_events,
    compute_overall_edges,
    compute_avg_session_edges,
    add_transition_probs,
)

MERGE_EVENTS = {"reviewed_merge", "self_merge"}
NO_MERGE_EVENTS = {"no_merge"}

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# Process ALL datasets every run
CONFIGS = {
    "branching": {
        "data_folder": os.path.join(ROOT, "data", "graph_labels"),
        "pattern": "*_labels_branching_and_structure.csv",
        "regex": re.compile(
            r"^(?:CLEAN_)?(year-long-project-team-\d+)_labels_branching_and_structure\.csv$",
            re.IGNORECASE,
        ),
        "example": "year-long-project-team-15_labels_branching_and_structure.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "branching_individual"),
        "mode": "branching",
    },
    "pr": {
        "data_folder": os.path.join(ROOT, "data", "csv"),
        "pattern": "*year-long-project-team-*.csv",
        "regex": re.compile(
            r"^(?:CLEAN_)?(?:pr_labels_)?(year-long-project-team-\d+)\.csv$",
            re.IGNORECASE,
        ),
        "example": "pr_labels_year-long-project-team-15.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "pr_individual"),
        "mode": "pr",
    },
    "communication": {
        "data_folder": os.path.join(ROOT, "data", "csv"),
        "pattern": "*year-long-project-team-*.csv",
        "regex": re.compile(
            r"^(?:CLEAN_)?(?:communication_labels_)?(year-long-project-team-\d+)\.csv$",
            re.IGNORECASE,
        ),
        "example": "communication_labels_year-long-project-team-15.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "communication_individual"),
        "mode": "communication",
    },
}


# Timestamp helpers
def parse_event_cell(ev) -> list[str]:
    import ast
    if ev is None or (isinstance(ev, float) and pd.isna(ev)):
        return []
    if isinstance(ev, list):
        return [e for e in ev if isinstance(e, str)]
    if isinstance(ev, str):
        s = ev.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [e for e in parsed if isinstance(e, str)]
            except Exception:
                pass
        return [s]
    return []


def pick_timestamp_row(row: pd.Series, events: list[str]) -> str | None:
    use_col = "created_at"
    if any(e in MERGE_EVENTS for e in events):
        use_col = "merged_at"
    elif any(e in NO_MERGE_EVENTS for e in events):
        use_col = "updated_at"

    val = row.get(use_col, None)
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        val = row.get("created_at", None)

    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        return None

    dt = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(dt):
        return str(val)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_timestamp_column(df: pd.DataFrame, fp: str) -> pd.DataFrame:
    if "timestamp" in df.columns:
        return df
    if "created_at" not in df.columns:
        raise KeyError(
            f"{fp} has no 'timestamp' and is missing 'created_at' so we can't derive timestamps.\n"
            f"Columns found: {sorted(df.columns)}"
        )

    timestamps: list[str | None] = []
    for _, row in df.iterrows():
        events = parse_event_cell(row.get("event"))
        timestamps.append(pick_timestamp_row(row, events))

    out = df.copy()
    out["timestamp"] = timestamps
    return out


def discover_team_files(config: dict) -> list[str]:
    search_pattern = os.path.join(config["data_folder"], config["pattern"])
    files = sorted(set(glob.glob(search_pattern)))
    if not files:
        raise FileNotFoundError(
            f"No label CSVs found in {config['data_folder']}\n"
            f"Expected e.g.: {os.path.join(config['data_folder'], config['example'])}"
        )
    return files


def parse_team_name_and_number(fp: str, team_re: re.Pattern) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = team_re.match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def norm_user(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def derive_user_non_branching(df: pd.DataFrame) -> pd.Series:
    """
    Generic user derivation used for pr + communication:
      - if source empty OR "pr" => pr_author
      - if source == "review"  => author
      - else fallback: pr_author then author
    """
    src = df.get("source")
    pr_author = df.get("pr_author")
    author = df.get("author")

    if src is None:
        src = pd.Series([""] * len(df), index=df.index)
    if pr_author is None:
        pr_author = pd.Series([""] * len(df), index=df.index)
    if author is None:
        author = pd.Series([""] * len(df), index=df.index)

    src_norm = src.astype(str).str.strip().str.lower().replace({"nan": ""})
    pr_author_norm = pr_author.astype(str).str.strip().replace({"nan": ""})
    author_norm = author.astype(str).str.strip().replace({"nan": ""})

    user = np.where(
        (src_norm == "") | (src_norm == "pr"),
        pr_author_norm,
        np.where(src_norm == "review", author_norm, np.where(pr_author_norm != "", pr_author_norm, author_norm)),
    )
    return pd.Series(user, index=df.index).astype(str).str.strip().replace({"nan": ""})


def explode_events_with_extras(df: pd.DataFrame, extra_cols: list[str]) -> pd.DataFrame:
    out = df.copy()

    out["pr_id"] = pd.to_numeric(out["pr_id"], errors="coerce").astype("Int64")
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)

    if "_row_idx" not in out.columns:
        out["_row_idx"] = np.arange(len(out))

    out["event_list"] = out["event"].apply(normalize_event_field)
    out = out.explode("event_list", ignore_index=True)
    out["event"] = out["event_list"].astype(str).str.strip()

    out = out.dropna(subset=["pr_id", "timestamp"])
    out = out[out["event"].ne("")]
    out = out.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    keep = ["pr_id", "timestamp", "event", "_row_idx"] + extra_cols
    keep = [c for c in keep if c in out.columns]
    return out[keep]


def load_csv_with_user(fp: str, mode: str) -> pd.DataFrame:
    raw = pd.read_csv(fp, low_memory=False)
    required = {"pr_id", "event"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    raw = ensure_timestamp_column(raw, fp)
    raw["timestamp"] = raw["timestamp"].astype(str).replace({"nan": ""}).str.strip()
    raw = raw[raw["timestamp"].ne("")].copy()

    if mode == "branching":
        if "pr_author" not in raw.columns:
            raise ValueError(f"{fp} missing required column for branching: pr_author")
        raw["user"] = raw["pr_author"].apply(norm_user)
    else:
        raw["user"] = derive_user_non_branching(raw)

    raw["user"] = raw["user"].astype(str).str.strip()
    raw = raw[raw["user"].ne("")].copy()

    raw["_row_idx"] = np.arange(len(raw))
    raw_u = explode_events_with_extras(raw, extra_cols=["user"])

    return raw_u[["pr_id", "timestamp", "event", "user"]].copy()


def process_dataset(dataset_name: str, config: dict) -> None:
    out_folder = config["output_folder"]
    os.makedirs(out_folder, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"Processing individual transitions: {dataset_name}")
    print(f"{'='*70}")
    print(f"[INFO] Output -> {out_folder}")

    files = discover_team_files(config)
    print(f"[INFO] Found {len(files)} files")

    all_overall: list[pd.DataFrame] = []
    all_avg: list[pd.DataFrame] = []
    all_freq: list[pd.DataFrame] = []
    sessions_rows: list[dict] = []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp, config["regex"])
        df = load_csv_with_user(fp, config["mode"])

        for user, udf in df.groupby("user", sort=False):
            freq = udf["event"].value_counts().reset_index()
            freq.columns = ["event", "count"]
            freq.insert(0, "user", user)
            freq.insert(0, "team_number", team_number)
            freq.insert(0, "team_name", team_name)
            all_freq.append(freq)

            overall_edges, n_sessions = compute_overall_edges(udf)
            avg_edges = compute_avg_session_edges(udf, n_sessions=n_sessions)

            overall_edges = add_transition_probs(overall_edges)
            avg_edges = add_transition_probs(avg_edges)

            for out_df in (overall_edges, avg_edges):
                out_df.insert(0, "user", user)
                out_df.insert(0, "team_number", team_number)
                out_df.insert(0, "team_name", team_name)

            all_overall.append(overall_edges)
            all_avg.append(avg_edges)

            sessions_rows.append(
                {"team_name": team_name, "team_number": team_number, "user": user, "num_pr_sessions": int(n_sessions)}
            )

    if not all_overall:
        print(f"[WARN] No metrics generated for {dataset_name}")
        return

    pd.concat(all_overall, ignore_index=True).to_csv(
        os.path.join(out_folder, "individual_transition_edges_overall.csv"), index=False
    )
    pd.concat(all_avg, ignore_index=True).to_csv(
        os.path.join(out_folder, "individual_transition_edges_avg_session.csv"), index=False
    )
    pd.DataFrame(sessions_rows).to_csv(
        os.path.join(out_folder, "individual_transition_sessions_count.csv"), index=False
    )
    pd.concat(all_freq, ignore_index=True).to_csv(
        os.path.join(out_folder, "individual_event_frequency.csv"), index=False
    )

    print(f"[OK] Wrote individual transition CSVs to: {out_folder}")


def main():
    for dataset_name, config in CONFIGS.items():
        process_dataset(dataset_name, config)


if __name__ == "__main__":
    main()