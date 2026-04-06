import os
import glob

import pandas as pd

from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing


OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "data/outputs")


def run_full_pipeline() -> dict:
    """
    Run the complete pipeline end-to-end:
    transition edges -> zscore -> clustering -> graphing.
    Returns a summary of what was produced.
    """
    run_transition_edges()
    run_zscore()
    run_clustering()
    run_graphing()

    return get_pipeline_summary()


def run_process_model_only() -> dict:
    """
    Re-run only clustering and graphing on existing data.
    Use this when labelled CSVs already exist and you don't
    need to re-run extraction or zscore steps.
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