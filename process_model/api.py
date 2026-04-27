import os
import glob

import pandas as pd

from event_labelling.CodeStructure_Branching.main import process_all_teams as run_branching_labels
from event_labelling.Communication.comm_label import process_all_teams as run_comm_labels
from event_labelling.PR.pr_label import process_all_teams as run_pr_labels

from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing


OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "data/outputs")


def run_full_pipeline() -> dict:
    """
    Run the complete pipeline end-to-end:
      1. Event labelling (branching, communication, PR)
      2. Transition edges
      3. Z-score calculation
      4. Clustering
      5. Graphing
    Returns a summary of what was produced.

    Requires raw data to already be present in data/csv/ (from unified_github_data_pull.py).
    """
    # Step 1: Event labelling — generates CLEAN_* CSVs
    print("\n" + "="*70)
    print("STEP 1a: BRANCHING & STRUCTURE LABELS")
    print("="*70)
    run_branching_labels()

    print("\n" + "="*70)
    print("STEP 1b: COMMUNICATION LABELS")
    print("="*70)
    run_comm_labels()

    print("\n" + "="*70)
    print("STEP 1c: PR LABELS")
    print("="*70)
    run_pr_labels()

    # Step 2-5: Process model
    print("\n" + "="*70)
    print("STEP 2: TRANSITION EDGES")
    print("="*70)
    run_transition_edges()

    print("\n" + "="*70)
    print("STEP 3: Z-SCORE CALCULATION")
    print("="*70)
    run_zscore()

    print("\n" + "="*70)
    print("STEP 4: CLUSTERING")
    print("="*70)
    run_clustering()

    print("\n" + "="*70)
    print("STEP 5: GRAPHING")
    print("="*70)
    run_graphing()

    return get_pipeline_summary()


def run_process_model_only() -> dict:
    """
    Re-run only clustering and graphing on existing data.
    Use this when CLEAN CSVs and transition edges already exist
    and you don't need to re-run labelling or extraction.
    """
    run_clustering()
    run_graphing()

    return get_pipeline_summary()


def get_pipeline_summary(output_root: str = OUTPUT_ROOT) -> dict:
    """
    Scan the output directories and return a structured summary
    of all generated PNGs, grouped by dataset.
    """
    datasets = ["branching", "pr", "communication"]
    summary = {}

    for dataset in datasets:
        dataset_dir = os.path.join(output_root, dataset)
        if not os.path.exists(dataset_dir):
            summary[dataset] = {"graph_count": 0, "graphs": []}
            continue

        pngs = sorted(glob.glob(os.path.join(dataset_dir, "**", "*.png"), recursive=True))
        summary[dataset] = {
            "graph_count": len(pngs),
            "graphs": [os.path.relpath(p, output_root) for p in pngs],
        }

    total = sum(d["graph_count"] for d in summary.values())
    return {"total_graphs": total, "by_dataset": summary}


def get_cluster_stats(output_root: str = OUTPUT_ROOT) -> dict:
    """
    Read the behavior_clusters_<dataset>.csv files produced by clustering.py
    and return a structured summary of cluster assignments per dataset.

    Each CSV has columns: team_number, cluster_id, k_used, silhouette.
    k_used and silhouette are the same for every row in a given CSV
    (one value per run), so we just read iloc[0].
    """
    datasets = ["branching", "pr", "communication"]
    result = {}

    for dataset in datasets:
        cluster_fp = os.path.join(output_root, dataset, f"behavior_clusters_{dataset}.csv")
        if not os.path.exists(cluster_fp):
            result[dataset] = None
            continue

        df = pd.read_csv(cluster_fp)
        result[dataset] = {
            "team_count": len(df),
            "cluster_count": int(df["cluster_id"].nunique()),
            "k_used": int(df["k_used"].iloc[0]) if "k_used" in df.columns else None,
            "silhouette": float(df["silhouette"].iloc[0]) if "silhouette" in df.columns else None,
            "clusters": (
                df.groupby("cluster_id")["team_number"]
                .apply(list)
                .to_dict()
            ),
        }

    return result