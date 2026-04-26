import os
import re
import ast
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph


# ---------- tiny utils ----------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def as_str_team(x) -> str:
    if pd.isna(x):
        return "unknown"
    s = str(x).strip()
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        return s.replace(".0", "")
    return s


def slugify_user(u: str) -> str:
    u = str(u).strip()
    if not u:
        return "unknown-user"
    u = u.lower()
    u = re.sub(r"\s+", "_", u)
    u = re.sub(r"[^a-z0-9_\-\.]+", "", u)
    return u or "unknown-user"


# ---------- event parsing ----------
def normalize_event_field(event):
    """
      - if event looks like a list string: "['a','b']" -> ['a','b']
      - otherwise: 'a' -> ['a']
    """
    if pd.isna(event):
        return []

    if isinstance(event, list):
        return [str(x).strip() for x in event if str(x).strip()]

    s = str(event).strip()
    if not s:
        return []

    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [str(parsed).strip()]
        except Exception:
            return [s]

    return [s]


def explode_and_sort_events(df: pd.DataFrame, keep_row_idx: bool = False) -> pd.DataFrame:
    """
    Expects columns: pr_id, timestamp, event
    Returns: pr_id, timestamp, event (exploded to 1 row per event)
    """
    df = df.copy()

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    # preserve existing row order key if caller already set it
    if "_row_idx" not in df.columns:
        df["_row_idx"] = np.arange(len(df))

    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]
    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    cols = ["pr_id", "timestamp", "event"]
    if keep_row_idx:
        cols.append("_row_idx")
    return df[cols]


# ---------- transition edges ----------
def compute_overall_edges(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    edge_counter = {}
    n_sessions = 0

    for pr_id, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if len(events) < 1:
            continue
        n_sessions += 1
        for i in range(len(events) - 1):
            a, b = events[i], events[i + 1]
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    overall_edges = pd.DataFrame(
        [{"from": a, "to": b, "count": c} for (a, b), c in edge_counter.items()]
    )
    return overall_edges, n_sessions


def compute_avg_session_edges(df: pd.DataFrame, n_sessions: int) -> pd.DataFrame:
    edge_counter = {}
    if n_sessions == 0:
        return pd.DataFrame(columns=["from", "to", "count"])

    for pr_id, g in df.groupby("pr_id", sort=False):
        events = g["event"].tolist()
        if len(events) < 1:
            continue
        seq = ["START"] + events + ["END"]
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            edge_counter[(a, b)] = edge_counter.get((a, b), 0) + 1

    return pd.DataFrame(
        [{"from": a, "to": b, "count": c / n_sessions} for (a, b), c in edge_counter.items()]
    )


def add_transition_probs(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.assign(prob=[])
    edges = edges.copy()
    edges["count"] = edges["count"].astype(float)
    denom = edges.groupby("from")["count"].transform("sum")
    edges["prob"] = np.where(denom > 0, edges["count"] / denom, 0.0)
    return edges


# ---------- rendering ----------
def build_markov_graph(user_label, edges_df, event_freq, output_path, title_suffix="", normalize_probs=True):
    edges_df = edges_df.copy()
    edges_df = edges_df[edges_df["count"] > 0]
    if edges_df.empty:
        print(f"[WARN] Skipping {user_label} — no edges.")
        return

    G = nx.DiGraph()
    for _, row in edges_df.iterrows():
        a, b, w = row["from"], row["to"], float(row["count"])
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
        else:
            G.add_edge(a, b, weight=w)

    for u, v in G.edges():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        G[u][v]["prob"] = G[u][v]["weight"] / total if normalize_probs and total else 0

    dot = Digraph(comment=f"Markov — {user_label}", format="png")
    dot.attr(
        rankdir="LR", size="8,5", splines="spline",
        nodesep="0.3", ranksep="0.3", pack="true", pad="0.2",
        margin="0", fontname="Helvetica"
    )
    dot.attr("node", shape="ellipse", style="filled", fontname="Helvetica", fontsize="12", width="2.0", height="1.0")
    dot.attr(
        "edge", color="#424242", arrowsize="0.8", fontname="Helvetica", fontsize="10",
        labelfontcolor="#000", penwidth="1.5"
    )

    for node in G.nodes():
        if node == "START":
            dot.node(
                str(node), label="START",
                fillcolor="#E57373", color="#B71C1C", fontcolor="white",
                shape="circle", style="filled,bold", penwidth="2",
                width="0.8", height="0.8", fixedsize="true"
            )
        elif node == "END":
            dot.node(
                str(node), label="END",
                fillcolor="#81C784", color="#1B5E20", fontcolor="white",
                shape="doublecircle", style="filled,bold", penwidth="2",
                width="0.8", height="0.8", fixedsize="true"
            )
        else:
            cnt = int(event_freq.get(node, 0)) if event_freq else 0
            node_label = str(node).replace("_", "\n")
            label = f"{node_label}\n{cnt}" if cnt > 0 else node_label
            dot.node(
                str(node), label=label,
                fillcolor="#90CAF9", color="#1E88E5", fontcolor="black",
                shape="ellipse", style="filled"
            )

    for u, v, data in G.edges(data=True):
        p = data.get("prob", 0.0)
        color = "#0D47A1" if p > 0.4 else "#1565C0" if p > 0.2 else "#64B5F6"
        dot.edge(str(u), str(v), label=f"{p:.2f}", color=color, penwidth=str(1.2 + p * 5))

    title = f"Markov Graph — {user_label}"
    if title_suffix:
        title += f" ({title_suffix})"
    dot.attr(label=title, labelloc="t", fontsize="14", fontname="Helvetica-Bold")
    dot.graph_attr.update(dpi="400")

    ensure_dir(os.path.dirname(output_path))
    dot.render(output_path.replace(".png", ""), cleanup=True)