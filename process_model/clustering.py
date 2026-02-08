import os
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# Load .env
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

# Configuration for both datasets
CONFIGS = {
    "branching": {
        "output_folder": os.path.join(ROOT, "data", "outputs", "branching"),
        "cluster_suffix": "branching"
    },
    "pr": {
        "output_folder": os.path.join(ROOT, "data", "outputs", "pr"),
        "cluster_suffix": "pr"
    }
}

Z_THRESHOLD = 1.645  # default is 1.645 for 90% confidence can adjust to 1.96 for 95% confidence


def filter_edges_by_zscore(df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    """
    Returns only edges with |z_score| >= cutoff (both tails).
    cutoff is an input parameter (not hardcoded inside this function).
    """
    if "z_score" not in df.columns:
        raise ValueError("Expected 'z_score' column in input; zscore_calculation.py should generate it.")
    return df[df["z_score"].abs() >= cutoff].copy()


def build_team_matrix(df: pd.DataFrame, z_threshold: float):
    df = df.copy()

    # vocab built from FULL df for stability
    pairs = sorted(set(zip(df["from"], df["to"])))
    pair_to_idx = {p: i for i, p in enumerate(pairs)}

    teams = sorted(df["team_number"].astype(str).unique(),
                   key=lambda x: int(x) if x.isdigit() else 999999)
    X = np.zeros((len(teams), len(pairs)), dtype=float)

    # ✅ apply threshold via function call
    df_filt = filter_edges_by_zscore(df, cutoff=z_threshold)

    for ti, team in enumerate(teams):
        g = df_filt[df_filt["team_number"].astype(str) == team]
        for _, r in g.iterrows():
            idx = pair_to_idx.get((r["from"], r["to"]))
            if idx is not None:
                X[ti, idx] = float(r["count"])

    return teams, pairs, X, df_filt


def compute_elbow_scores(X: np.ndarray, k_min=2, k_max=10):
    """Compute inertia (within-cluster sum of squares) for elbow method.
    
    Args:
        X: Data matrix (n_samples, n_features)
        k_min: Minimum number of clusters
        k_max: Maximum number of clusters
    
    Returns:
        Dictionary with k values and corresponding inertias
    """
    n = X.shape[0]
    k_max = min(k_max, n - 1)
    
    elbow_data = {"k": [], "inertia": []}
    
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, n_init=25, random_state=42)
        km.fit(X)
        elbow_data["k"].append(k)
        elbow_data["inertia"].append(km.inertia_)
    
    return elbow_data


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
    # Process both datasets
    for dataset_name, config in CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"Processing: {dataset_name}")
        print(f"{'='*70}")
        
        data_dir = config["output_folder"]
        cluster_suffix = config["cluster_suffix"]
        in_fp = os.path.join(data_dir, "team_transition_edges_avg_session_zscores.csv")
        out_fp = os.path.join(data_dir, f"behavior_clusters_{cluster_suffix}.csv")
        matrix_out_fp = os.path.join(data_dir, f"team_transition_matrix_{cluster_suffix}.csv")
        filtered_edges_out_fp = os.path.join(
            data_dir, f"team_transition_edges_avg_session_zfiltered_{cluster_suffix}.csv"
        )
        
        if not os.path.exists(in_fp):
            print(f"[SKIP] Missing input: {in_fp}")
            print(f"       Run zscore_calculation.py first")
            continue
        
        print(f"[INFO] Loading data from: {in_fp}")
        df = pd.read_csv(in_fp, low_memory=False)
        
        print("[INFO] Building team matrix...")
        teams, pairs, X, df_filt = build_team_matrix(df, z_threshold=Z_THRESHOLD)

        nonzero_mask = (X.sum(axis=1) > 0)
        kept_teams = [t for t, keep in zip(teams, nonzero_mask) if keep]
        X = X[nonzero_mask]
        
        dropped = int((~nonzero_mask).sum())
        if dropped:
            print(f"[INFO] Dropped {dropped} teams with all-zero vectors at |z| ≥ {Z_THRESHOLD}")

        # export z-filtered edges for kept teams
        df_filt = df_filt.copy()
        df_filt["team_number"] = df_filt["team_number"].astype(str)
        df_filt_kept = df_filt[df_filt["team_number"].isin(set(map(str, kept_teams)))].copy()

        cols_first = ["team_number", "from", "to", "count", "z_score"]
        remaining = [c for c in df_filt_kept.columns if c not in cols_first]
        df_filt_kept = df_filt_kept[cols_first + remaining]
        df_filt_kept.to_csv(filtered_edges_out_fp, index=False)
        print(f"[OK] Wrote z-filtered edges: {filtered_edges_out_fp}")

        # export transition matrix
        col_names = [f"{a}->{b}" for (a, b) in pairs]
        matrix_df = pd.DataFrame(X, index=kept_teams, columns=col_names)
        matrix_df.index.name = "team_number"
        matrix_df.to_csv(matrix_out_fp)
        print(f"[OK] Wrote transition matrix: {matrix_out_fp}")

        if X.shape[0] < 2:
            out = pd.DataFrame({"team_number": kept_teams, "cluster_id": [0] * len(kept_teams)})
            out.to_csv(out_fp, index=False)
            print(f"[OK] Wrote: {out_fp} (not enough teams to cluster)")
            continue

        print("[INFO] Performing clustering...")
        best_k, best_sil = choose_best_k(X)
        elbow_scores = None
        if X.shape[0] >= 3:
            elbow_scores = compute_elbow_scores(X)
        else:
            print("[INFO] Skipping elbow scores (need >= 3 teams).")
        km = KMeans(n_clusters=best_k, n_init=25, random_state=42)
        clusters = km.fit_predict(X)

        out = pd.DataFrame({
            "team_number": kept_teams,
            "cluster_id": clusters,
            "k_used": best_k,
            "silhouette": best_sil if best_sil is not None else np.nan,
        })
        out.to_csv(out_fp, index=False)
        print(f"[OK] Wrote: {out_fp}")
        
        # Save elbow scores
        if elbow_scores and elbow_scores.get("k"):
            elbow_fp = os.path.join(data_dir, f"elbow_scores_{cluster_suffix}.csv")
            elbow_df = pd.DataFrame(elbow_scores)
            elbow_df.to_csv(elbow_fp, index=False)
            print(f"[OK] Wrote: {elbow_fp}")
        else:
            print("[INFO] Skipping elbow CSV (no valid k range).")


if __name__ == "__main__":
    main()