# process_model/zscore_filter_team_graph.py
"""
One-command script:
  python -m process_model.zscore_filter_team_graph

Hardcoded inputs (PR outputs):
  data/outputs/pr/team_transition_edges_avg_session.csv
  data/outputs/pr/team_event_frequency.csv

Outputs:
  data/outputs/pr/team_transition_edges_avg_session_zscores_team{TEAM}.csv
  data/outputs/pr/team_transition_edges_avg_session_zfiltered_team{TEAM}.csv
  data/outputs/pr/year-long-project-team-{TEAM}/team_zfiltered_avg_session/team{TEAM}_avg_session_zfiltered.png
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
from graphviz import Digraph


# =========================
# EDIT THESE IF YOU WANT
# =========================
TEAM_NUMBER: str | None = None     # e.g. "7" (if None, you'll be prompted)
Z_THRESHOLD: float = 1.645 # 1.645 ≈ 90% two-tailed cutoff; try 1.96 for 95%
# =========================


# -----------------------------
# Paths (hardcoded to PR output)
# -----------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

PR_OUT_DIR = os.path.join(ROOT, "data", "outputs", "pr")
IN_AVG_FP = os.path.join(PR_OUT_DIR, "team_transition_edges_avg_session.csv")
IN_FREQ_FP = os.path.join(PR_OUT_DIR, "team_event_frequency.csv")


# -----------------------------
# Helpers (no nested functions)
# -----------------------------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _as_str_team(x) -> str:
    if pd.isna(x):
        return "unknown"
    s = str(x).strip()
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        return s.replace(".0", "")
    return s


def _parse_team_selector(team_raw: str) -> str:
    s = (team_raw or "").strip()
    m = re.search(r"team-(\d+)", s)
    if m:
        return m.group(1)
    return s


def load_team_event_freq(freq_fp: str, team_number: str) -> dict:
    """
    Returns: {event: count_int} for one team.
    """
    if not os.path.exists(freq_fp):
        return {}
    df = pd.read_csv(freq_fp, low_memory=False)
    required = {"team_number", "event", "count"}
    if not required.issubset(df.columns):
        return {}

    df = df.copy()
    df["team_number"] = df["team_number"].apply(_as_str_team)
    df = df[df["team_number"] == str(team_number)]
    if df.empty:
        return {}

    df["event"] = df["event"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return dict(zip(df["event"], df["count"]))


def compute_team_zscores(team_edges: pd.DataFrame) -> pd.DataFrame:
    """
    Z-scores across THIS TEAM's edge weights (count), ddof=0 (matches your pipeline).
    """
    out = team_edges.copy()
    out["count"] = pd.to_numeric(out["count"], errors="coerce").astype(float).fillna(0.0)

    c = out["count"].astype(float)
    mean = float(c.mean())
    std = float(c.std(ddof=0))

    if std == 0.0 or np.isclose(std, 0.0) or np.isnan(std):
        out["z_score"] = 0.0
    else:
        out["z_score"] = (c - mean) / std

    out["abs_z"] = out["z_score"].abs()
    return out


def filter_by_zscore(df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    if "z_score" not in df.columns:
        raise ValueError("Expected 'z_score' column.")
    return df[df["z_score"].abs() >= float(cutoff)].copy()


def build_markov_graph(
    user_label: str,
    edges_df: pd.DataFrame,
    event_freq: dict,
    output_path: str,
    title_suffix: str = "",
    normalize_probs: bool = True,
):
    edges_df = edges_df.copy()
    edges_df["count"] = pd.to_numeric(edges_df["count"], errors="coerce").fillna(0.0).astype(float)
    edges_df = edges_df[edges_df["count"] > 0]

    if edges_df.empty:
        print(f"[WARN] Skipping {user_label} — no edges.")
        return

    # Build directed graph with weights
    G = nx.DiGraph()
    for _, row in edges_df.iterrows():
        a, b, w = str(row["from"]), str(row["to"]), float(row["count"])
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
        else:
            G.add_edge(a, b, weight=w)

    # Probabilities (per 'from')
    for u, v in G.edges():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        G[u][v]["prob"] = (G[u][v]["weight"] / total) if (normalize_probs and total) else 0.0

    # Render
    dot = Digraph(comment=f"Markov — {user_label}", format="png")
    dot.attr(
        rankdir="LR", size="8,5", splines="spline",
        nodesep="0.3", ranksep="0.3", pack="true", pad="0.2",
        margin="0", fontname="Helvetica"
    )
    dot.attr("node", shape="ellipse", style="filled", fontname="Helvetica", fontsize="12",
             width="2.0", height="1.0")
    dot.attr("edge", color="#424242", arrowsize="0.8", fontname="Helvetica", fontsize="10",
             labelfontcolor="#000", penwidth="1.5")

    for node in G.nodes():
        if node == "START":
            dot.node(
                node, label="START",
                fillcolor="#E57373", color="#B71C1C", fontcolor="white",
                shape="circle", style="filled,bold", penwidth="2",
                width="0.8", height="0.8", fixedsize="true"
            )
        elif node == "END":
            dot.node(
                node, label="END",
                fillcolor="#81C784", color="#1B5E20", fontcolor="white",
                shape="doublecircle", style="filled,bold", penwidth="2",
                width="0.8", height="0.8", fixedsize="true"
            )
        else:
            cnt = int(event_freq.get(node, 0)) if event_freq else 0
            node_label = node.replace("_", "\n")
            label = f"{node_label}\n{cnt}" if cnt > 0 else node_label
            dot.node(
                node, label=label,
                fillcolor="#90CAF9", color="#1E88E5", fontcolor="black",
                shape="ellipse", style="filled"
            )

    for u, v, data in G.edges(data=True):
        p = float(data.get("prob", 0.0))
        color = "#0D47A1" if p > 0.4 else "#1565C0" if p > 0.2 else "#64B5F6"
        dot.edge(str(u), str(v), label=f"{p:.2f}", color=color, penwidth=str(1.2 + p * 5))

    title = f"Markov Graph — {user_label}"
    if title_suffix:
        title += f" ({title_suffix})"
    dot.attr(label=title, labelloc="t", fontsize="14", fontname="Helvetica-Bold")
    dot.graph_attr.update(dpi="400")

    ensure_dir(os.path.dirname(output_path))
    dot.render(output_path.replace(".png", ""), cleanup=True)


# -----------------------------
# Main
# -----------------------------
def main():
    if not os.path.exists(IN_AVG_FP):
        raise FileNotFoundError(
            f"Missing required input:\n  {IN_AVG_FP}\n"
            f"Run transition_edges.py first to generate team_transition_edges_avg_session.csv."
        )

    team = TEAM_NUMBER
    if team is None:
        team = input("Team number (e.g., 7): ").strip()
    team = _parse_team_selector(team)
    if not team:
        raise ValueError("Team number cannot be empty.")

    print(f"[CONFIG] Using PR outputs folder: {PR_OUT_DIR}")
    print(f"[CONFIG] Team={team}  Z_THRESHOLD={Z_THRESHOLD}")

    df = pd.read_csv(IN_AVG_FP, low_memory=False)
    required = {"team_number", "from", "to", "count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {IN_AVG_FP}: {missing}")

    df = df.copy()
    df["team_number"] = df["team_number"].apply(_as_str_team)
    df["from"] = df["from"].astype(str)
    df["to"] = df["to"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

    team_df = df[df["team_number"] == str(team)].copy()
    if team_df.empty:
        avail = sorted(df["team_number"].unique().tolist(), key=lambda x: int(x) if str(x).isdigit() else 999999)
        raise ValueError(f"No rows for team_number='{team}'. Available teams (sample): {avail[:25]}")

    # z-score + export
    team_z = compute_team_zscores(team_df)
    team_z = team_z.sort_values(["abs_z", "count"], ascending=[False, False]).reset_index(drop=True)

    out_z_fp = os.path.join(PR_OUT_DIR, f"team_transition_edges_avg_session_zscores_team{team}.csv")
    team_z.to_csv(out_z_fp, index=False)
    print(f"[OK] Wrote team z-scores: {out_z_fp}")

    # filter + export
    zf = filter_by_zscore(team_z, cutoff=Z_THRESHOLD)
    zf = zf.sort_values(["abs_z", "count"], ascending=[False, False]).reset_index(drop=True)

    out_zf_fp = os.path.join(PR_OUT_DIR, f"team_transition_edges_avg_session_zfiltered_team{team}.csv")
    zf.to_csv(out_zf_fp, index=False)

    kept, total = len(zf), len(team_z)
    pct = (kept / total * 100.0) if total else 0.0
    print(f"[OK] Wrote team z-filtered edges: {out_zf_fp} ({kept}/{total} kept = {pct:.1f}%)")

    if zf.empty:
        print(f"[WARN] No edges survived |z| >= {Z_THRESHOLD}. PNG will not be generated.")
        return

    # render PNG
    event_freq = load_team_event_freq(IN_FREQ_FP, team_number=str(team))

    team_dir = os.path.join(PR_OUT_DIR, f"year-long-project-team-{team}")
    out_png_dir = os.path.join(team_dir, "team_zfiltered_avg_session")
    out_png_fp = os.path.join(out_png_dir, f"team{team}_avg_session_zfiltered.png")

    build_markov_graph(
        user_label=f"Team {team}",
        edges_df=zf[["from", "to", "count"]].copy(),
        event_freq=event_freq,
        output_path=out_png_fp,
        title_suffix=f"Z-filtered Avg Session • pr • |z|≥{Z_THRESHOLD}",
        normalize_probs=True,
    )

    print(f"[OK] Wrote PNG: {out_png_fp}")


if __name__ == "__main__":
    main()