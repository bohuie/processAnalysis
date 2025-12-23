import os
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
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
FOLDER_SOURCE = os.getenv("FOLDER_SOURCE")  # default: "branching"
# ============================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# Determine input/output paths based on FOLDER_SOURCE
if FOLDER_SOURCE == "branching":
    DATA_DIR = os.path.join(ROOT, "data", "outputs", "branching")
    CLUSTER_SUFFIX = "branching"
    print("[CONFIG] Processing branching data from data/outputs/branching/")
elif FOLDER_SOURCE == "pr":
    DATA_DIR = os.path.join(ROOT, "data", "outputs", "pr")
    CLUSTER_SUFFIX = "pr"
    print("[CONFIG] Processing PR data from data/outputs/pr/")
else:
    raise ValueError(f"Invalid FOLDER_SOURCE: {FOLDER_SOURCE}. Must be 'branching' or 'pr'")

IN_FP = os.path.join(DATA_DIR, "team_transition_edges_avg_session_zscores.csv")
OUT_FP = os.path.join(DATA_DIR, f"behavior_clusters_{CLUSTER_SUFFIX}.csv")

Z_THRESHOLD = 1.645  # pick in clustering, not zscore script

def build_team_matrix(df: pd.DataFrame, z_threshold: float):
    df = df.copy()

    # vocab built from FULL df for stability
    pairs = sorted(set(zip(df["from"], df["to"])))
    pair_to_idx = {p: i for i, p in enumerate(pairs)}

    teams = sorted(df["team_number"].astype(str).unique(),
                   key=lambda x: int(x) if x.isdigit() else 999999)
    X = np.zeros((len(teams), len(pairs)), dtype=float)

    # apply threshold here
    if "z_score" in df.columns:
        df = df[df["z_score"] >= z_threshold].copy()
    else:
        raise ValueError("Expected 'z_score' column in input; zscore_calculation.py should generate it.")

    for ti, team in enumerate(teams):
        g = df[df["team_number"].astype(str) == team]
        for _, r in g.iterrows():
            idx = pair_to_idx.get((r["from"], r["to"]))
            if idx is not None:
                X[ti, idx] = float(r["count"])

    return teams, pairs, X


def choose_best_k(X: np.ndarray, k_min=2, k_max=10):
    n = X.shape[0]
    if n < 3:
        return 2, None

    k_max = min(k_max, n - 1)
    best_k, best_score = 2, -1

    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, n_init=25, random_state=42)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_k = k

    return best_k, best_score

def main():
    if not os.path.exists(IN_FP):
        raise FileNotFoundError(
            f"Missing required input: {IN_FP}\n"
            f"Run zscore_calculation.py first with FOLDER_SOURCE='{FOLDER_SOURCE}'"
        )
    
    print(f"[INFO] Loading data from: {IN_FP}")
    df = pd.read_csv(IN_FP, low_memory=False)
    
    print("[INFO] Building team matrix...")
    teams, pairs, X = build_team_matrix(df, z_threshold=Z_THRESHOLD)

    nonzero_mask = (X.sum(axis=1) > 0)
    teams = [t for t, keep in zip(teams, nonzero_mask) if keep]
    X = X[nonzero_mask]
    
    dropped = int((~nonzero_mask).sum())
    if dropped:
        print(f"[INFO] Dropped {dropped} teams with all-zero vectors at z ≥ {Z_THRESHOLD}")


    if X.shape[0] < 2:
        out = pd.DataFrame({"team_number": teams, "cluster_id": [0] * len(teams)})
        out.to_csv(OUT_FP, index=False)
        print(f"[OK] Wrote: {OUT_FP} (not enough teams to cluster)")
        return

    print("[INFO] Performing clustering...")
    best_k, best_sil = choose_best_k(X)
    km = KMeans(n_clusters=best_k, n_init=25, random_state=42)
    clusters = km.fit_predict(X)

    out = pd.DataFrame({
        "team_number": teams,
        "cluster_id": clusters,
        "k_used": best_k,
        "silhouette": best_sil if best_sil is not None else np.nan,
    })
    out.to_csv(OUT_FP, index=False)
    print(f"[OK] Wrote: {OUT_FP}")

if __name__ == "__main__":
    main()