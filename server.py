"""
FastAPI service to run the analysis pipeline and serve generated graph PNGs from disk.

Env vars:
  OUTPUT_ROOT=data/outputs
  AI_MODE=offline|online (pipeline controls)
  API_KEY=your-secret-key
"""

import os
import glob
import datetime
from pathlib import Path
from typing import List, Tuple

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import Response
from fastapi.security.api_key import APIKeyHeader

from process_model.api import (
    run_full_pipeline,
    get_pipeline_summary,
    get_cluster_stats,
)
from process_model.transition_edges import main as run_transition_edges
from process_model.zscore_calculation import main as run_zscore
from process_model.clustering import main as run_clustering
from process_model.graphing import main as run_graphing

app = FastAPI(title="Process Analysis Graph Service", version="2.0.0")

OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "data/outputs")
API_KEY = os.getenv("API_KEY", "dev-secret-key")


# ============================================================
# ERROR HELPERS
# ============================================================

def error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={
        "error": code,
        "message": message,
        "status": status,
    })


# ============================================================
# AUTH
# ============================================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        error(401, "UNAUTHORIZED", "missing or invalid API key")


# ============================================================
# DISK HELPERS
# ============================================================

def detect_dataset_and_team(path: str) -> Tuple[str, str]:
    dataset = "unknown"
    team = "unknown"
    parts = Path(path).parts
    if "branching" in parts:
        dataset = "branching"
    elif "communication" in parts:
        dataset = "communication"
    elif "pr" in parts:
        dataset = "pr"
    elif "communication" in parts:
        dataset = "communication"
    for p in parts:
        if p.endswith(".png"):
            continue
        if p.startswith("year-long-project-team-"):
            team = p
            break
        if p.startswith("cluster"):
            team = p
            break
    return dataset, team


def collect_pngs(root: str) -> List[str]:
    pattern = os.path.join(root, "**", "*.png")
    return sorted(glob.glob(pattern, recursive=True))


def get_graph_list(root: str = OUTPUT_ROOT) -> List[dict]:
    """
    Scan the output directory and return a list of graph metadata dicts.
    Uses the relative file path as the stable identifier (no DB needed).
    """
    pngs = collect_pngs(root)
    result = []
    for fp in pngs:
        rel = os.path.relpath(fp, root)
        dataset, team = detect_dataset_and_team(fp)
        result.append({
            "file_path": rel,
            "dataset": dataset,
            "team": team,
        })
    return result


# ============================================================
# HEALTH (no auth needed)
# ============================================================

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat() + "Z"}


# ============================================================
# PIPELINE
# ============================================================

@app.post("/pipeline/run", dependencies=[Depends(require_api_key)])
def pipeline_run():
    try:
        summary = run_full_pipeline()
        return {"status": "ok", "total_graphs": summary["total_graphs"]}
    except HTTPException:
        raise
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"full pipeline failed: {exc}")


@app.post("/pipeline/run/transition-edges", dependencies=[Depends(require_api_key)])
def pipeline_run_transition_edges():
    try:
        run_transition_edges()
        return {"status": "ok", "step": "transition_edges"}
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"transition_edges failed: {exc}")


@app.post("/pipeline/run/zscore", dependencies=[Depends(require_api_key)])
def pipeline_run_zscore():
    try:
        run_zscore()
        return {"status": "ok", "step": "zscore"}
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"zscore failed: {exc}")


@app.post("/pipeline/run/clustering", dependencies=[Depends(require_api_key)])
def pipeline_run_clustering():
    try:
        run_clustering()
        return {"status": "ok", "step": "clustering"}
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"clustering failed: {exc}")


@app.post("/pipeline/run/graphing", dependencies=[Depends(require_api_key)])
def pipeline_run_graphing():
    try:
        run_graphing()
        return {"status": "ok", "step": "graphing"}
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"graphing failed: {exc}")


@app.get("/pipeline/summary", dependencies=[Depends(require_api_key)])
def pipeline_summary():
    try:
        return get_pipeline_summary()
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"failed to get pipeline summary: {exc}")


# ============================================================
# GRAPHS
# ============================================================

@app.get("/graphs/count", dependencies=[Depends(require_api_key)])
def graphs_count():
    try:
        graphs = get_graph_list()
        return {"count": len(graphs)}
    except Exception as exc:
        error(500, "INTERNAL_ERROR", f"failed to count graphs: {exc}")


@app.get("/graphs/list", dependencies=[Depends(require_api_key)])
def graphs_list(limit: int = 50):
    limit = max(1, min(limit, 500))
    try:
        graphs = get_graph_list()
        return {"items": graphs[:limit]}
    except Exception as exc:
        error(500, "INTERNAL_ERROR", f"failed to list graphs: {exc}")


@app.get("/graphs/metrics", dependencies=[Depends(require_api_key)])
def graphs_metrics():
    try:
        graphs = get_graph_list()
        by_dataset: dict = {}
        graphs_per_team: dict = {}

        for g in graphs:
            dataset = g["dataset"]
            team = g["team"]
            by_dataset[dataset] = by_dataset.get(dataset, 0) + 1
            if dataset not in graphs_per_team:
                graphs_per_team[dataset] = {}
            graphs_per_team[dataset][team] = graphs_per_team[dataset].get(team, 0) + 1

        teams_per_dataset = {d: len(teams) for d, teams in graphs_per_team.items()}

        return {
            "total_graphs": len(graphs),
            "by_dataset": by_dataset,
            "teams_per_dataset": teams_per_dataset,
            "graphs_per_team": graphs_per_team,
        }
    except Exception as exc:
        error(500, "INTERNAL_ERROR", f"failed to get metrics: {exc}")


@app.get("/graphs/image", dependencies=[Depends(require_api_key)])
def graph_image(path: str):
    """
    Serve a PNG by its relative file path.
    Example: GET /graphs/image?path=pr/year-long-project-team-1/team1_avg_session.png
    Use /graphs/list to get valid paths.
    """
    safe_path = os.path.normpath(os.path.join(OUTPUT_ROOT, path))
    if not safe_path.startswith(os.path.abspath(OUTPUT_ROOT)):
        error(400, "INVALID_PATH", "path traversal not allowed")
    if not os.path.isfile(safe_path):
        error(404, "NOT_FOUND", f"graph not found: {path}")
    with open(safe_path, "rb") as f:
        return Response(content=f.read(), media_type="image/png")


# ============================================================
# CLUSTERS
# ============================================================

@app.get("/clusters/stats", dependencies=[Depends(require_api_key)])
def clusters_stats():
    try:
        return get_cluster_stats()
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"failed to get cluster stats: {exc}")