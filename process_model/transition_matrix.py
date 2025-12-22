import os, re, glob
import pandas as pd
import numpy as np
import ast

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION SWITCH - Choose which files to process
# ============================================================
# Set to "branching" or "pr_labels"
FILE_SOURCE = "branching"  # or "pr_labels"
# ============================================================

# Configuration for branching_and_structure files
BRANCHING_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "graph_labels", "clean"),
    "prefix": "CLEAN_year-long-project-team-",
    "pattern": "*_labels_branching_and_structure.csv",
    "regex": re.compile(r"^CLEAN_(year-long-project-team-\d+)_labels_branching_and_structure\.csv$", re.IGNORECASE),
    "example": "CLEAN_year-long-project-team-7_labels_branching_and_structure.csv"
}

# Configuration for pr_labels files
PR_LABELS_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "csv"),
    "prefix": "CLEAN_pr_labels_",
    "pattern": "year-long-project-team-*.csv",
    "regex": re.compile(r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE),
    "example": "CLEAN_pr_labels_year-long-project-team-7.csv"
}

# Select active configuration
if FILE_SOURCE == "branching":
    CONFIG = BRANCHING_CONFIG
    print("[CONFIG] Using branching_and_structure files from data/graph_labels/clean/")
elif FILE_SOURCE == "pr_labels":
    CONFIG = PR_LABELS_CONFIG
    print("[CONFIG] Using pr_labels files from data/csv/")
else:
    raise ValueError(f"Invalid FILE_SOURCE: {FILE_SOURCE}. Must be 'branching' or 'pr_labels'")

DATA_FOLDER = CONFIG["data_folder"]
CLEAN_PREFIX = CONFIG["prefix"]
TEAM_RE = CONFIG["regex"]

OUT_FOLDER = os.path.join(ROOT, "data", "outputs", "pr")
os.makedirs(OUT_FOLDER, exist_ok=True)

def discover_clean_team_files() -> list[str]:
    search_pattern = os.path.join(DATA_FOLDER, f"{CLEAN_PREFIX}{CONFIG['pattern']}")
    hits = glob.glob(search_pattern)
    files = sorted(set(hits))
    if not files:
        raise FileNotFoundError(
            f"No CLEAN label CSVs found in {DATA_FOLDER}\n"
            f"Expected e.g.: {os.path.join(DATA_FOLDER, CONFIG['example'])}\n"
            f"Current FILE_SOURCE setting: '{FILE_SOURCE}'\n"
            f"Change FILE_SOURCE in the script to switch between 'branching' and 'pr_labels'"
        )
    return files

def parse_team_name_and_number(fp: str) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = TEAM_RE.match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def normalize_event_field(event):
    """
    Old-graphing behavior:
      - if event looks like a list string: "['a','b']" -> ['a','b']
      - otherwise: 'a' -> ['a']
    """
    if pd.isna(event):
        return []

    # if it's already a list (rare, but safe)
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
            # fall back: treat as a single event string
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

    # keep original row order so list-elements keep deterministic ordering
    df["_row_idx"] = np.arange(len(df))

    # parse event into list, then explode to one-event-per-row (old graphing behavior)
    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)

    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]

    # IMPORTANT: stable sort to preserve within-timestamp ordering
    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    return df[["pr_id", "timestamp", "event"]]


def compute_overall_edges_old_style(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Matches old compute_edge_counts(flat):
      - per PR session, count transitions event[i] -> event[i+1]
      - NO START/END
      - pooled counts across PR sessions
    """
    edge_counter = {}
    n_sessions = 0

    for pr_id, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if len(events) < 1:
            continue
        n_sessions += 1
        for i in range(len(events) - 1):
            a, b = events[i], events[i + 1]
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    overall_edges = pd.DataFrame(
        [{"from": a, "to": b, "count": c} for (a, b), c in edge_counter.items()]
    )
    return overall_edges, n_sessions

def compute_avg_session_edges_old_style(df: pd.DataFrame, n_sessions: int) -> pd.DataFrame:
    """
    Matches old compute_avg_session_edges(flat):
      - per PR session, include START->first and last->END
      - pooled counts then divide by n_sessions
    """
    edge_counter = {}

    if n_sessions == 0:
        return pd.DataFrame(columns=["from", "to", "count"])

    for pr_id, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if len(events) < 1:
            continue
        seq = ["START"] + events + ["END"]
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    avg_edges = pd.DataFrame(
        [{"from": a, "to": b, "count": c / n_sessions} for (a, b), c in edge_counter.items()]
    )
    return avg_edges

def add_transition_probs(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.assign(prob=[])
    edges = edges.copy()
    edges["count"] = edges["count"].astype(float)
    denom = edges.groupby("from")["count"].transform("sum")
    edges["prob"] = np.where(denom > 0, edges["count"] / denom, 0.0)
    return edges

def main():
    files = discover_clean_team_files()
    print(f"[INFO] Found {len(files)} CLEAN team files:")
    for f in files:
        print(" -", f)

    all_overall, all_avg, all_freq, sessions_rows = [], [], [], []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp)
        df = load_noholes_csv(fp)

        # event frequency for labels (old script used flat event counts)
        freq = df["event"].value_counts().reset_index()
        freq.columns = ["event", "count"]
        freq.insert(0, "team_number", team_number)
        freq.insert(0, "team_name", team_name)
        all_freq.append(freq)

        overall_edges, n_sessions = compute_overall_edges_old_style(df)
        avg_edges = compute_avg_session_edges_old_style(df, n_sessions=n_sessions)

        overall_edges = add_transition_probs(overall_edges)
        avg_edges = add_transition_probs(avg_edges)

        overall_edges.insert(0, "team_name", team_name)
        overall_edges.insert(1, "team_number", team_number)

        avg_edges.insert(0, "team_name", team_name)
        avg_edges.insert(1, "team_number", team_number)

        all_overall.append(overall_edges)
        all_avg.append(avg_edges)

        sessions_rows.append({
            "team_name": team_name,
            "team_number": team_number,
            "num_pr_sessions": int(n_sessions)
        })

    pd.concat(all_overall, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "team_transition_edges_overall.csv"), index=False
    )
    pd.concat(all_avg, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "team_transition_edges_avg_session.csv"), index=False
    )
    pd.DataFrame(sessions_rows).to_csv(
        os.path.join(OUT_FOLDER, "team_transition_sessions_count.csv"), index=False
    )
    pd.concat(all_freq, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "team_event_frequency.csv"), index=False
    )

    print("[OK] Wrote transition CSVs to:", OUT_FOLDER)

if __name__ == "__main__":
    main()