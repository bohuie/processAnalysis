import os, re, glob
import pandas as pd
import numpy as np
import ast

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION - Process BOTH branching and PR data
# ============================================================

BRANCHING_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "graph_labels", "clean"),
    "prefix": "CLEAN_year-long-project-team-",
    "pattern": "*_labels_branching_and_structure.csv",
    "regex": re.compile(r"^CLEAN_(year-long-project-team-\d+)_labels_branching_and_structure\.csv$", re.IGNORECASE),
    "example": "CLEAN_year-long-project-team-7_labels_branching_and_structure.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "branching"),
}

PR_LABELS_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "csv"),
    "prefix": "CLEAN_pr_labels_",
    "pattern": "year-long-project-team-*.csv",
    "regex": re.compile(r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE),
    "example": "CLEAN_pr_labels_year-long-project-team-7.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "pr"),
}

COMM_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "csv"),
    "prefix": "CLEAN_communication_labels_",
    "pattern": "year-long-project-team-*.csv",
    "regex": re.compile(r"^CLEAN_communication_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE),
    "example": "CLEAN_communication_labels_year-long-project-team-7.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "communication"),
}

CONFIGS = {
    "branching": BRANCHING_CONFIG,
    "pr_labels": PR_LABELS_CONFIG,
}


# ============================================================
# HELPERS
# ============================================================

def discover_clean_team_files(config: dict) -> list[str]:
    search_pattern = os.path.join(config["data_folder"], f"{config['prefix']}{config['pattern']}")
    files = sorted(set(glob.glob(search_pattern)))
    if not files:
        raise FileNotFoundError(
            f"No CLEAN label CSVs found in {config['data_folder']}\n"
            f"Expected e.g.: {os.path.join(config['data_folder'], config['example'])}"
        )
    return files


def parse_team_name_and_number(fp: str, config: dict) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = config["regex"].match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def normalize_event_field(event) -> list[str]:
    """
    Normalizes an event cell to a list of event strings.
      - list string "['a','b']" -> ['a', 'b']
      - plain string 'a'        -> ['a']
      - NaN / empty             -> []
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


def load_noholes_csv(fp: str) -> pd.DataFrame:
    df = pd.read_csv(fp, low_memory=False)
    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["_row_idx"] = np.arange(len(df))

    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]
    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    return df[["pr_id", "timestamp", "event"]]


# ============================================================
# EDGE COMPUTATION
# ============================================================

def compute_overall_edges(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Per-PR transitions (no START/END), pooled counts.
    Returns (edges_df, n_sessions).
    """
    edge_counter: dict[tuple, int] = {}
    n_sessions = 0

    for _, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if not events:
            continue
        n_sessions += 1
        for a, b in zip(events, events[1:]):
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    edges = pd.DataFrame(
        [{"from": a, "to": b, "count": c} for (a, b), c in edge_counter.items()]
    )
    return edges, n_sessions


def compute_avg_session_edges(df: pd.DataFrame, n_sessions: int) -> pd.DataFrame:
    """
    Per-PR transitions with START->first and last->END.
    Counts divided by n_sessions to give per-session averages.
    """
    if n_sessions == 0:
        return pd.DataFrame(columns=["from", "to", "count"])

    edge_counter: dict[tuple, int] = {}

    for _, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if not events:
            continue
        seq = ["START"] + events + ["END"]
        for a, b in zip(seq, seq[1:]):
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    return pd.DataFrame(
        [{"from": a, "to": b, "count": c / n_sessions} for (a, b), c in edge_counter.items()]
    )


def add_transition_probs(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.assign(prob=[])
    edges = edges.copy()
    edges["count"] = edges["count"].astype(float)
    denom = edges.groupby("from")["count"].transform("sum")
    edges["prob"] = np.where(denom > 0, edges["count"] / denom, 0.0)
    return edges


# ============================================================
# MAIN
# ============================================================

def main():
    for dataset_name, config in CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"Processing: {dataset_name}")
        print(f"{'='*70}")

        out_folder = config["output_folder"]
        os.makedirs(out_folder, exist_ok=True)

        try:
            files = discover_clean_team_files(config)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")
            continue

        print(f"[INFO] Found {len(files)} CLEAN team files")

        all_overall, all_avg, all_freq, sessions_rows = [], [], [], []

        for fp in files:
            team_name, team_number = parse_team_name_and_number(fp, config)
            df = load_noholes_csv(fp)

            freq = df["event"].value_counts().reset_index()
            freq.columns = ["event", "count"]
            freq.insert(0, "team_number", team_number)
            freq.insert(0, "team_name", team_name)
            all_freq.append(freq)

            overall_edges, n_sessions = compute_overall_edges(df)
            avg_edges = compute_avg_session_edges(df, n_sessions=n_sessions)

            overall_edges = add_transition_probs(overall_edges)
            avg_edges = add_transition_probs(avg_edges)

            for df_out in (overall_edges, avg_edges):
                df_out.insert(0, "team_name", team_name)
                df_out.insert(1, "team_number", team_number)

            all_overall.append(overall_edges)
            all_avg.append(avg_edges)
            sessions_rows.append({
                "team_name": team_name,
                "team_number": team_number,
                "num_pr_sessions": int(n_sessions),
            })

        pd.concat(all_overall, ignore_index=True).to_csv(
            os.path.join(out_folder, "team_transition_edges_overall.csv"), index=False
        )
        pd.concat(all_avg, ignore_index=True).to_csv(
            os.path.join(out_folder, "team_transition_edges_avg_session.csv"), index=False
        )
        pd.DataFrame(sessions_rows).to_csv(
            os.path.join(out_folder, "team_transition_sessions_count.csv"), index=False
        )
        pd.concat(all_freq, ignore_index=True).to_csv(
            os.path.join(out_folder, "team_event_frequency.csv"), index=False
        )

        print(f"[OK] Wrote {dataset_name} transition CSVs to: {out_folder}")


if __name__ == "__main__":
    main()