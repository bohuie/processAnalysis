"""
FastAPI service to run the analysis pipeline and store generated graph PNGs into Postgres.
Services expected (docker-compose):
- app (this service)
- db (Postgres)
- llm (Ollama, optional; pipeline uses AI_MODE env toggle)

Env vars:
  DATABASE_URL=postgresql://user:pass@host:port/dbname
  OUTPUT_ROOT=data/outputs
  AI_MODE=offline|online (pipeline controls)
  API_KEY=your-secret-key
"""

import os
import glob
import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import psycopg2
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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/graphs")
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
# DB HELPERS
# ============================================================

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS graphs (
    id SERIAL PRIMARY KEY,
    dataset TEXT NOT NULL,
    team TEXT,
    file_path TEXT UNIQUE NOT NULL,
    image BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

UPSERT_SQL = """
INSERT INTO graphs (dataset, team, file_path, image, updated_at)
VALUES (%s, %s, %s, %s, NOW())
ON CONFLICT (file_path)
DO UPDATE SET image = EXCLUDED.image, updated_at = NOW();
"""


def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as exc:
        error(503, "SERVICE_UNAVAILABLE", f"database connection failed: {exc}")


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(TABLE_SQL)
    conn.commit()


def detect_dataset_and_team(path: str) -> Tuple[str, str]:
    dataset = "unknown"
    team = "unknown"
    parts = Path(path).parts
    if "branching" in parts:
        dataset = "branching"
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


def store_graphs(conn, root: str) -> int:
    ensure_table(conn)
    pngs = collect_pngs(root)
    if not pngs:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for fp in pngs:
            dataset, team = detect_dataset_and_team(fp)
            with open(fp, "rb") as f:
                blob = f.read()
            cur.execute(UPSERT_SQL, (dataset, team, os.path.relpath(fp, root), blob))
            inserted += 1
    conn.commit()
    return inserted


def run_pipeline_and_store():
    run_full_pipeline()
    conn = get_conn()
    try:
        count = store_graphs(conn, OUTPUT_ROOT)
    finally:
        conn.close()
    return count


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
        count = run_pipeline_and_store()
        return {"status": "ok", "stored": count}
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
    conn = get_conn()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM graphs;")
            row = cur.fetchone()
            n = row[0] if row else 0
        return {"count": n}
    finally:
        conn.close()


@app.get("/graphs/list", dependencies=[Depends(require_api_key)])
def graphs_list(limit: int = 50):
    limit = max(1, min(limit, 500))
    conn = get_conn()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, dataset, team, file_path, updated_at FROM graphs ORDER BY updated_at DESC LIMIT %s;",
                (limit,),
            )
            rows = cur.fetchall()
        return {
            "items": [
                {
                    "id": r[0],
                    "dataset": r[1],
                    "team": r[2],
                    "file_path": r[3],
                    "updated_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/graphs/metrics", dependencies=[Depends(require_api_key)])
def graphs_metrics():
    conn = get_conn()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM graphs;")
            row = cur.fetchone()
            total_graphs = row[0] if row else 0

            cur.execute(
                "SELECT dataset, COUNT(*) FROM graphs GROUP BY dataset ORDER BY dataset;"
            )
            dataset_rows = cur.fetchall()

            cur.execute(
                "SELECT dataset, team, COUNT(*) FROM graphs GROUP BY dataset, team ORDER BY dataset, team;"
            )
            team_rows = cur.fetchall()

        by_dataset: Dict[str, int] = {row[0]: row[1] for row in dataset_rows}
        teams_per_dataset: Dict[str, int] = {}
        graphs_per_team: Dict[str, Dict[str, int]] = {}

        for dataset, team, count in team_rows:
            if dataset not in graphs_per_team:
                graphs_per_team[dataset] = {}
            graphs_per_team[dataset][team] = count

        for dataset, team_map in graphs_per_team.items():
            teams_per_dataset[dataset] = len(team_map)

        return {
            "total_graphs": total_graphs,
            "by_dataset": by_dataset,
            "teams_per_dataset": teams_per_dataset,
            "graphs_per_team": graphs_per_team,
        }
    finally:
        conn.close()


@app.get("/graphs/{graph_id}", dependencies=[Depends(require_api_key)])
def graph_detail(graph_id: int):
    conn = get_conn()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, dataset, team, file_path, updated_at FROM graphs WHERE id = %s;",
                (graph_id,),
            )
            row = cur.fetchone()
        if not row:
            error(404, "NOT_FOUND", f"graph with id {graph_id} not found")
        return {
            "id": row[0],
            "dataset": row[1],
            "team": row[2],
            "file_path": row[3],
            "updated_at": row[4].isoformat() if row[4] else None,
        }
    finally:
        conn.close()


@app.get("/graphs/{graph_id}/image", dependencies=[Depends(require_api_key)])
def graph_image(graph_id: int):
    conn = get_conn()
    try:
        ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image FROM graphs WHERE id = %s;",
                (graph_id,),
            )
            row = cur.fetchone()
        if not row:
            error(404, "NOT_FOUND", f"graph with id {graph_id} not found")
        return Response(content=bytes(row[0]), media_type="image/png")
    finally:
        conn.close()


# ============================================================
# CLUSTERS
# ============================================================

@app.get("/clusters/stats", dependencies=[Depends(require_api_key)])
def clusters_stats():
    try:
        return get_cluster_stats()
    except Exception as exc:
        error(500, "PIPELINE_FAILED", f"failed to get cluster stats: {exc}")