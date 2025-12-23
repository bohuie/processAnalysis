import os
from pathlib import Path
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# ============================================================
# CONFIGURATION SWITCH - Choose which folder to process
# ============================================================
# Set to "branching" or "pr"
# Can be set via environment variable: FOLDER_SOURCE=branching python ...
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
FOLDER_SOURCE = os.getenv("FOLDER_SOURCE")
FILE_SOURCE = os.getenv("FILE_SOURCE")
# ============================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# Determine input/output paths based on FOLDER_SOURCE
if FOLDER_SOURCE == "branching":
    DATA_DIR = os.path.join(ROOT, "data", "outputs", "branching")
    print("[CONFIG] Processing branching data from data/outputs/branching/")
elif FOLDER_SOURCE == "pr":
    DATA_DIR = os.path.join(ROOT, "data", "outputs", "pr")
    print("[CONFIG] Processing PR data from data/outputs/pr/")
else:
    raise ValueError(f"Invalid FOLDER_SOURCE: {FOLDER_SOURCE}. Must be 'branching' or 'pr'")

IN_FP = os.path.join(DATA_DIR, "team_transition_edges_avg_session.csv")
OUT_FP = os.path.join(DATA_DIR, "team_transition_edges_avg_session_zscores.csv")


def zscore_per_team(edges: pd.DataFrame, team_col: str) -> pd.DataFrame:
    edges = edges.copy()
    edges["count"] = pd.to_numeric(edges["count"], errors="coerce").astype(float)

    def apply_group(g: pd.DataFrame) -> pd.DataFrame:
        c = g["count"].astype(float)
        mean = c.mean()
        std = c.std(ddof=0)

        if std == 0 or np.isclose(std, 0.0) or np.isnan(std):
            g["z_score"] = 0.0
        else:
            g["z_score"] = (c - mean) / std

        return g

    return edges.groupby(team_col, group_keys=False).apply(apply_group)


def main():
    if not os.path.exists(IN_FP):
        raise FileNotFoundError(
            f"Missing required input: {IN_FP}\n"
            f"Run transition_matrix.py first with FILE_SOURCE='{FOLDER_SOURCE}'"
        )
    
    print(f"[INFO] Loading data from: {IN_FP}")
    edges = pd.read_csv(IN_FP, low_memory=False)

    required = {"from", "to", "count"}
    missing = required - set(edges.columns)
    if missing:
        raise ValueError(f"Missing columns in {IN_FP}: {missing}")

    # support either team_number or team_name
    if "team_number" in edges.columns:
        team_col = "team_number"
    elif "team_name" in edges.columns:
        team_col = "team_name"
    else:
        raise ValueError(f"Missing team identifier column. Expected 'team_number' or 'team_name' in {IN_FP}.")

    print("[INFO] Computing z-scores...")
    out = zscore_per_team(edges, team_col=team_col)
    out.to_csv(OUT_FP, index=False)
    print(f"[OK] Wrote: {OUT_FP}")


if __name__ == "__main__":
    main()