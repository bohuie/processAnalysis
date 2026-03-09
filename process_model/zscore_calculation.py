import os
import pandas as pd
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# Process ALL datasets every run
CONFIGS = {
    "branching": {"output_folder": os.path.join(ROOT, "data", "outputs", "branching")},
    "pr": {"output_folder": os.path.join(ROOT, "data", "outputs", "pr")},
    "communication": {"output_folder": os.path.join(ROOT, "data", "outputs", "communication")},
}


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
    for dataset_name, config in CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"Processing: {dataset_name}")
        print(f"{'='*70}")

        data_dir = config["output_folder"]
        in_fp = os.path.join(data_dir, "team_transition_edges_avg_session.csv")
        out_fp = os.path.join(data_dir, "team_transition_edges_avg_session_zscores.csv")

        if not os.path.exists(in_fp):
            print(f"[SKIP] Missing input: {in_fp}")
            print("       Run transition_edges.py first")
            continue

        print(f"[INFO] Loading data from: {in_fp}")
        edges = pd.read_csv(in_fp, low_memory=False)

        required = {"from", "to", "count"}
        missing = required - set(edges.columns)
        if missing:
            print(f"[ERROR] Missing columns in {in_fp}: {missing}")
            continue

        # support either team_number or team_name
        if "team_number" in edges.columns:
            team_col = "team_number"
        elif "team_name" in edges.columns:
            team_col = "team_name"
        else:
            print(f"[ERROR] Missing team identifier column in {in_fp}")
            continue

        print("[INFO] Computing z-scores...")
        out = zscore_per_team(edges, team_col=team_col)
        out.to_csv(out_fp, index=False)
        print(f"[OK] Wrote: {out_fp}")


if __name__ == "__main__":
    main()