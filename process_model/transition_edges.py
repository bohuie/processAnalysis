import os, re, glob
import pandas as pd
import numpy as np
import ast
from pathlib import Path
from dotenv import load_dotenv
from src.utils.markov_common import (
    explode_and_sort_events,
    compute_overall_edges,
    compute_avg_session_edges,
    add_transition_probs,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION SWITCH - Choose which files to process
# ============================================================
# Set to "branching" or "pr_labels"
# Can be set via environment variable: FILE_SOURCE=branching python ...
script_path = Path(__file__).resolve()
print(f"[DEBUG] Script location: {script_path}")

env_path = script_path.parent.parent / '.env'
print(f"[DEBUG] Looking for .env at: {env_path}")
print(f"[DEBUG] .env exists: {env_path.exists()}")

# Load it
load_dotenv(dotenv_path=env_path)

# Check what was loaded
print(f"[DEBUG] FILE_SOURCE = {os.getenv('FILE_SOURCE')}")
print(f"[DEBUG] FOLDER_SOURCE = {os.getenv('FOLDER_SOURCE')}")

FILE_SOURCE = os.getenv("FILE_SOURCE")
# ============================================================

# Configuration for branching_and_structure files
BRANCHING_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "graph_labels", "clean"),
    "prefix": "CLEAN_year-long-project-team-",
    "pattern": "*_labels_branching_and_structure.csv",
    "regex": re.compile(r"^CLEAN_(year-long-project-team-\d+)_labels_branching_and_structure\.csv$", re.IGNORECASE),
    "example": "CLEAN_year-long-project-team-7_labels_branching_and_structure.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "branching")
}

# Configuration for pr_labels files
PR_LABELS_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "csv"),
    "prefix": "CLEAN_pr_labels_",
    "pattern": "year-long-project-team-*.csv",
    "regex": re.compile(r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE),
    "example": "CLEAN_pr_labels_year-long-project-team-7.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "pr")
}

# Select active configuration
if FILE_SOURCE == "branching":
    CONFIG = BRANCHING_CONFIG
    print("[CONFIG] Using branching_and_structure files from data/graph_labels/clean/")
    print(f"[CONFIG] Output will be saved to: {CONFIG['output_folder']}")
elif FILE_SOURCE == "pr_labels":
    CONFIG = PR_LABELS_CONFIG
    print("[CONFIG] Using pr_labels files from data/csv/")
    print(f"[CONFIG] Output will be saved to: {CONFIG['output_folder']}")
else:
    raise ValueError(f"Invalid FILE_SOURCE: {FILE_SOURCE}. Must be 'branching' or 'pr_labels'")

DATA_FOLDER = CONFIG["data_folder"]
CLEAN_PREFIX = CONFIG["prefix"]
TEAM_RE = CONFIG["regex"]
OUT_FOLDER = CONFIG["output_folder"]

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

def load_noholes_csv(fp: str) -> pd.DataFrame:
    df = pd.read_csv(fp, low_memory=False)
    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")
    return explode_and_sort_events(df)

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

        overall_edges, n_sessions = compute_overall_edges(df)
        avg_edges = compute_avg_session_edges(df, n_sessions=n_sessions)

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