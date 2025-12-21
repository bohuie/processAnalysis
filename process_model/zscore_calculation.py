import os
import pandas as pd
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

IN_FP = os.path.join(ROOT, "data", "outputs", "pr", "team_transition_edges_avg_session.csv")
OUT_FP = os.path.join(ROOT, "data", "outputs", "pr", "team_transition_edges_avg_session_zscores.csv")


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

    out = zscore_per_team(edges, team_col=team_col)
    out.to_csv(OUT_FP, index=False)
    print(f"[OK] Wrote: {OUT_FP}")


if __name__ == "__main__":
    main()

