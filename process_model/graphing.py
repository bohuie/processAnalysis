# ============================================================
# graphing.py — PR Markov Graph Visualizer (CSV -> PNG only)
# ============================================================

import os
import argparse
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph
from dotenv import load_dotenv
from pathlib import Path

# ============================================================

# ============================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

script_path = Path(__file__).resolve()
env_path = script_path.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Configuration for both datasets
CONFIGS = {
    "branching": {
        "output_folder": os.path.join(ROOT, "data", "outputs", "branching"),
        "category_label": "branching"
    },
    "pr": {
        "output_folder": os.path.join(ROOT, "data", "outputs", "pr"),
        "category_label": "pr"
    }
}

# ---------- Tiny utils ----------
def _wrap_team_list(teams: list[str], max_line_len: int = 70, max_teams: int = 40) -> str:
    teams = [str(t) for t in teams]
    n = len(teams)

    if n > max_teams:
        shown = teams[:max_teams]
        suffix = f", … (+{n - max_teams} more)"
    else:
        shown = teams
        suffix = ""

    prefix = f"Teams (n={n}): "
    lines = []
    cur = prefix
    for t in shown:
        piece = ("" if cur.endswith(": ") else ", ") + t
        if len(cur) + len(piece) > max_line_len and cur != prefix:
            lines.append(cur)
            cur = " " * len(prefix) + t
        else:
            cur += piece
    lines.append(cur + suffix)
    return "\n".join(lines)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _as_str_team(x) -> str:
    if pd.isna(x):
        return "unknown"
    s = str(x).strip()
    # handle "7.0" etc
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        return s.replace(".0", "")
    return s


def load_event_freq_map(freq_fp: str) -> dict:
    """
    Returns: {team_number_str: {event: count_int}}
    """
    if not os.path.exists(freq_fp):
        return {}
    df = pd.read_csv(freq_fp, low_memory=False)
    required = {"team_number", "event", "count"}
    if not required.issubset(df.columns):
        return {}

    df = df.copy()
    df["team_number"] = df["team_number"].apply(_as_str_team)
    df["event"] = df["event"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)

    out = {}
    for team, g in df.groupby("team_number"):
        out[team] = dict(zip(g["event"], g["count"]))
    return out


def load_sessions_count_map(sess_fp: str) -> dict:
    """
    Returns: {team_number_str: num_pr_sessions_int}
    """
    if not os.path.exists(sess_fp):
        return {}
    df = pd.read_csv(sess_fp, low_memory=False)
    required = {"team_number", "num_pr_sessions"}
    if not required.issubset(df.columns):
        return {}

    df = df.copy()
    df["team_number"] = df["team_number"].apply(_as_str_team)
    df["num_pr_sessions"] = pd.to_numeric(df["num_pr_sessions"], errors="coerce").fillna(0).astype(int)
    return dict(zip(df["team_number"], df["num_pr_sessions"]))


# ---------- Cross-team IDF edge pruning (3-pass) ----------
import math as _math


class _DSU:
    """
    Disjoint Set Union (Union-Find) with path compression + union-by-rank.
    Used by repair_connectivity (Pass 2).
    """
    def __init__(self, nodes):
        self._parent = {n: n for n in nodes}
        self._rank   = {n: 0 for n in nodes}

    def find(self, x):
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x, y) -> bool:
        """Merge x and y. Returns True iff they were in different components."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1
        return True

    def same(self, x, y) -> bool:
        return self.find(x) == self.find(y)


def build_edge_idf_map(all_teams_df: pd.DataFrame, min_count: int = 2) -> tuple:
    """
    Compute a cross-team Inverse Document Frequency (IDF) map for edges.

    An edge (u->v) is "present" in a team if that team's count >= min_count.
    IDF rewards edges that appear in few teams (distinctive) and penalises
    edges that appear in many teams (common).

        idf[(u,v)] = log((N+1) / (df+1)) + 1    (smooth, always positive)

    Edges not meeting the presence threshold in any team receive the neutral
    value 1.0 to avoid amplifying noise.

    Parameters
    ----------
    all_teams_df : DataFrame with columns team_number, from, to, count
    min_count    : minimum count to consider an edge "present" in a team

    Returns
    -------
    (idf_map, N)
        idf_map : dict {(from_node, to_node): idf_float}
        N       : int  number of distinct teams
    """
    df = all_teams_df.copy()
    N = int(df["team_number"].nunique())
    if N == 0:
        return {}, 0

    present = df[df["count"] >= min_count][["team_number", "from", "to"]].drop_duplicates()
    doc_freq = present.groupby(["from", "to"]).size()  # Series indexed by (from, to)

    idf_map: dict = {}
    for (u, v), dfe in doc_freq.items():
        idf_map[(str(u), str(v))] = _math.log((N + 1) / (dfe + 1)) + 1
    # Missing edges (below threshold or absent) default to neutral 1.0
    return idf_map, N


def score_team_edges(
    G: nx.DiGraph,
    idf_map: dict,
    strength_mode: str = "prob",
) -> dict:
    """
    Compute a distinctiveness score for every edge in G.

        score[(u,v)] = strength * idf

    strength = G[u][v]["prob"]   if strength_mode == "prob"  (default)
             = G[u][v]["weight"] if strength_mode == "count"

    IDF for edges not in idf_map defaults to 1.0 (neutral).

    Returns dict {(u, v): score}.
    """
    scores: dict = {}
    for u, v, data in G.edges(data=True):
        idf = idf_map.get((str(u), str(v)), 1.0)
        if strength_mode == "prob":
            strength = data.get("prob", 0.0)
        else:
            strength = data.get("weight", 0.0)
        scores[(u, v)] = strength * idf
    return scores


def prune_team_edges_distinctive(
    G: nx.DiGraph,
    scores: dict,
    top_k: int = 1,
    score_min: float | None = None,
) -> set:
    """
    Pass 1 — distinctiveness-based pruning.

    For each source node u (iterated in sorted order for determinism):
      - Sort outgoing edges by (-score, -weight, str(v)).
      - Keep edge (u->v) if it is in the top-K outgoing edges for u,
        or if score >= score_min (when score_min is set).

    Top-K guarantees every node that has outgoing edges retains at least
    min(top_k, out_degree) of them.  Pass 3 handles fully isolated nodes.

    Returns set of (u, v) pairs to draw.
    """
    keep: set = set()

    for u in sorted(G.nodes(), key=str):
        out_edges = list(G.out_edges(u, data=True))
        if not out_edges:
            continue

        # Sort: best score first; tie-break by weight then target name.
        out_sorted = sorted(
            out_edges,
            key=lambda e: (-scores.get((e[0], e[1]), 0.0), -e[2]["weight"], str(e[1])),
        )

        for rank, (uu, vv, _data) in enumerate(out_sorted):
            pair = (uu, vv)
            sc   = scores.get(pair, 0.0)
            if rank < top_k:
                keep.add(pair)          # always keep top-K
            elif score_min is not None and sc >= score_min:
                keep.add(pair)          # also keep if above threshold

    return keep


def repair_connectivity(
    keep_set: set,
    G: nx.DiGraph,
    scores: dict,
    all_nodes: set,
) -> tuple:
    """
    Pass 2 — greedy connectivity repair using DSU.

    Treats the pruned edge set as an undirected graph.  If more than one
    weakly-connected component exists among all_nodes, adds back the
    minimum number of original edges (bridge candidates) needed to
    reach a single component.

    Bridge candidates are sorted by (-score, -weight, str(u), str(v))
    for determinism.

    Uses an integer `remaining` counter (not num_components() per loop)
    for O(alpha) convergence check.

    Returns (updated_keep_set, n_comp_before, edges_added).
    """
    dsu = _DSU(sorted(all_nodes, key=str))
    for u, v in keep_set:
        dsu.union(u, v)

    n_comp_before = len({dsu.find(n) for n in all_nodes})
    remaining     = n_comp_before
    edges_added   = 0

    if remaining > 1:
        candidates = sorted(
            [
                (u, v, data["weight"])
                for u, v, data in G.edges(data=True)
                if (u, v) not in keep_set
            ],
            key=lambda e: (-scores.get((e[0], e[1]), 0.0), -e[2], str(e[0]), str(e[1])),
        )
        for u, v, _w in candidates:
            if remaining == 1:
                break
            if dsu.union(u, v):          # True → were in different components
                keep_set.add((u, v))
                edges_added += 1
                remaining   -= 1

    n_comp_after = len({dsu.find(n) for n in all_nodes})
    return keep_set, n_comp_before, n_comp_after, edges_added


def fix_orphans(
    keep_set: set,
    G: nx.DiGraph,
    scores: dict,
    all_nodes: set,
) -> tuple:
    """
    Pass 3 — orphan guardrail.

    Any node with degree 0 in the undirected sense of the pruned edge set
    gets its single strongest incident edge (in or out) restored from the
    original graph.  Iteration order is sorted for determinism.

    Returns (updated_keep_set, orphan_count_fixed).
    """
    incident: set = set()
    for u, v in keep_set:
        incident.add(u)
        incident.add(v)
    orphans = sorted(all_nodes - incident, key=str)

    fixes = 0
    for node in orphans:
        candidates = [
            (u, v, data["weight"])
            for u, v, data in G.out_edges(node, data=True)
        ] + [
            (u, v, data["weight"])
            for u, v, data in G.in_edges(node, data=True)
        ]
        if not candidates:
            continue
        best_u, best_v, _ = min(
            candidates,
            key=lambda e: (
                -scores.get((e[0], e[1]), 0.0),
                -e[2],
                str(e[0]),
                str(e[1]),
            ),
        )
        keep_set.add((best_u, best_v))
        fixes += 1

    return keep_set, fixes


# ---------- Rendering ----------
def build_markov_graph(user_label, edges_df, event_freq, output_path,
                       title_suffix="", normalize_probs=True,
                       teams_in_cluster=None, config=None,
                       idf_map=None, n_teams=1):
    edges_df = edges_df.copy()
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

    # Probabilities (needed before scoring)
    for u, v in G.edges():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        G[u][v]["prob"] = G[u][v]["weight"] / total if normalize_probs and total else 0.0

    # ---- IDF distinctiveness pruning (3-pass) ----
    orientation   = getattr(config, "orientation", "horizontal")
    top_k_cli     = getattr(config, "top_k", None)   # None means auto
    top_k         = top_k_cli if top_k_cli is not None else (2 if orientation == "vertical" else 1)
    score_min     = getattr(config, "score_min", None)
    preserve_conn = getattr(config, "preserve_connectivity", True)
    idf_map       = idf_map or {}

    # Score: prob × idf  (strength_mode=prob; degrades to weight if prob==0)
    scores = score_team_edges(G, idf_map, strength_mode="prob")

    all_nodes = set(G.nodes())
    edges_before = G.number_of_edges()

    # Pass 1
    keep_set  = prune_team_edges_distinctive(G, scores, top_k=top_k, score_min=score_min)
    p1_count  = len(keep_set)

    if preserve_conn:
        # Pass 2
        keep_set, n_comp_p1, n_comp_after, bridges = repair_connectivity(keep_set, G, scores, all_nodes)
        conn_count = len(keep_set)
        # Pass 3
        keep_set, orphan_fixes = fix_orphans(keep_set, G, scores, all_nodes)
    else:
        n_comp_p1 = n_comp_after = bridges = conn_count = orphan_fixes = 0
        conn_count = p1_count

    final_count = len(keep_set)

    # Diagnostics
    tag = f"[PRUNE] {user_label}:"
    print(
        f"{tag} {edges_before} edges"
        f" → P1:{p1_count}"
        f" → Conn:{conn_count} (+{bridges} bridges)"
        f" → Final:{final_count} (+{orphan_fixes} orphan fixes)"
        f"  |  components: {n_comp_p1}→{n_comp_after}"
        f"  |  top_k={top_k}, score_min={score_min}"
    )
    if n_comp_after > 1:
        print(f"[WARN] {user_label}: {n_comp_after} component(s) remain — original graph may be disconnected.")

    # Draw
    dot = Digraph(comment=f"Markov — {user_label}", format="png")
    
    # Defaults tailored for orientation
    orientation = config.orientation if config else "horizontal"
    
    if orientation == "vertical":
        rankdir = "TB"
        graph_size = config.size if (config and config.size) else "10,14"
        nodesep, ranksep = "0.35", "0.55"
        font_node, font_edge, font_title = "14", "12", "16"
    else:
        # Default / Horizontal
        rankdir = "LR"
        graph_size = config.size if (config and config.size) else "12,6"
        nodesep, ranksep = "0.3", "0.3"
        font_node, font_edge, font_title = "12", "10", "14"

    dot.attr(
        rankdir=rankdir, size=graph_size, splines="spline",
        nodesep=nodesep, ranksep=ranksep, pack="true", pad="0.2",
        margin="0", fontname="Helvetica"
    )
    dot.attr("node", shape="ellipse", style="filled", fontname="Helvetica", fontsize=font_node, width="2.0", height="1.0")
    dot.attr(
        "edge", color="#424242", arrowsize="0.8", fontname="Helvetica", fontsize=font_edge,
        labelfontcolor="#000", penwidth="1.5"
    )

    for node in sorted(G.nodes(), key=str):
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
            fillcolor, fontcolor = "#90CAF9", "black"
            cnt = int(event_freq.get(node, 0)) if event_freq else 0
            node_label = str(node).replace("_", "\n")
            label = f"{node_label}\n{cnt}" if cnt > 0 else node_label
            dot.node(
                str(node), label=label,
                fillcolor=fillcolor, color="#1E88E5", fontcolor=fontcolor,
                shape="ellipse", style="filled"
            )

    for u, v, data in G.edges(data=True):
        # Skip edges removed by IDF pruning.
        if (u, v) not in keep_set:
            continue

        p = data.get("prob", 0.0)

        # Secondary visual filter: fixed minimum probability threshold.
        min_prob = getattr(config, "min_edge_prob", 0.0)
        if p < min_prob:
            continue

        color = "#0D47A1" if p > 0.4 else "#1565C0" if p > 0.2 else "#64B5F6"
        # HTML-like label with padding to distance text from the line
        label_html = f'<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0"><TR><TD CELLPADDING="4">{p:.2f}</TD></TR></TABLE>>'
        dot.edge(str(u), str(v), label=label_html, color=color, penwidth=str(1.2 + p * 5))

    title = f"Markov Graph — {user_label}"
    if title_suffix:
        title += f" ({title_suffix})"
    if teams_in_cluster:
        title += "\n" + _wrap_team_list(teams_in_cluster)

    dot.attr(label=title, labelloc="t", fontsize="14", fontname="Helvetica-Bold")

    dot.graph_attr.update(dpi="400")

    ensure_dir(os.path.dirname(output_path))
    dot.render(output_path.replace(".png", ""), cleanup=True)


# ---------- Team graphs ----------
def render_team_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict,
                       out_teams_dir: str, category_label: str, config=None,
                       overall_idf: dict = None, avg_idf: dict = None, n_teams: int = 1):
    """
    Render per-team overall and avg-session Markov graphs.

    IDF maps are computed ONCE by the caller (main) from all teams' data
    and passed in here — never recomputed per team.
    """
    overall_idf = overall_idf or {}
    avg_idf     = avg_idf     or {}

    teams = sorted(set(overall_df["team_number"]).union(set(avg_df["team_number"])),
                   key=lambda x: int(x) if str(x).isdigit() else 999999)

    for team in teams:
        team_str = _as_str_team(team)
        team_dir = os.path.join(out_teams_dir, f"year-long-project-team-{team_str}")
        out_overall_dir = os.path.join(team_dir, "team_overall")
        out_avg_dir     = os.path.join(team_dir, "team_avg_session")
        ensure_dir(out_overall_dir)
        ensure_dir(out_avg_dir)

        event_freq = freq_map.get(team_str, {})

        # Overall (no START/END expected)
        t_overall = overall_df[overall_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_overall,
            event_freq=event_freq,
            output_path=os.path.join(out_overall_dir, f"team{team_str}_overall.png"),
            title_suffix=f"Overall • {category_label}",
            config=config,
            idf_map=overall_idf,
            n_teams=n_teams,
        )

        # Avg session (START/END expected)
        t_avg = avg_df[avg_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"team{team_str}_avg_session.png"),
            title_suffix=f"Avg Session • {category_label}",
            config=config,
            idf_map=avg_idf,
            n_teams=n_teams,
        )


# ---------- Cluster graphs (optional) ----------
def _aggregate_cluster_edges(edges_df: pd.DataFrame, teams: list[str], sess_count: dict) -> pd.DataFrame:
    """
    Session-weighted aggregation over an edge-list DF with columns:
      team_number, from, to, count

    cluster_total = sum(team_count * team_sessions)
    cluster_avg   = cluster_total / sum(team_sessions)
    """
    total_weight = 0
    acc = {}

    for t in teams:
        w = int(sess_count.get(t, 0))
        if w <= 0:
            w = 1
        total_weight += w

        sub = edges_df[edges_df["team_number"] == t]
        for _, r in sub.iterrows():
            key = (r["from"], r["to"])
            acc[key] = acc.get(key, 0.0) + float(r["count"]) * w

    if total_weight <= 0:
        total_weight = 1

    rows = [{"from": a, "to": b, "count": c / total_weight} for (a, b), c in acc.items()]
    return pd.DataFrame(rows)


def _aggregate_cluster_event_freq(freq_map: dict, teams: list[str]) -> dict:
    out = {}
    for t in teams:
        for ev, c in freq_map.get(t, {}).items():
            out[ev] = out.get(ev, 0) + int(c)
    return out


def render_cluster_graphs(zfilt_df: pd.DataFrame, freq_map: dict, sess_count: dict,
                          in_cluster_fp: str, out_clusters_dir: str, category_label: str,
                          config=None, idf_map: dict = None, n_teams: int = 1):
    """
    Render cluster Markov graphs using the SAME global IDF map as team graphs
    (computed from overall_df in main).  Overlap is measured against the full
    team population, not just the cluster subset.
    """
    if not os.path.exists(in_cluster_fp):
        print(f"[INFO] No cluster CSV found at {in_cluster_fp} — skipping cluster graphs.")
        return

    cdf = pd.read_csv(in_cluster_fp, low_memory=False)
    required = {"team_number", "cluster_id"}
    if not required.issubset(cdf.columns):
        print("[WARN] Cluster CSV missing required columns — skipping cluster graphs.")
        return

    cdf = cdf.copy()
    cdf["team_number"] = cdf["team_number"].apply(_as_str_team)
    cdf["cluster_id"] = pd.to_numeric(cdf["cluster_id"], errors="coerce").fillna(0).astype(int)

    ensure_dir(out_clusters_dir)

    for cluster_id, g in cdf.groupby("cluster_id"):
        teams = sorted(g["team_number"].tolist(), key=lambda x: int(x) if x.isdigit() else 999999)

        cluster_edges = _aggregate_cluster_edges(zfilt_df, teams, sess_count)
        cluster_freq = _aggregate_cluster_event_freq(freq_map, teams)

        # match old naming style: cluster1, cluster2, ...
        human_cluster = int(cluster_id) + 1
        cdir = os.path.join(out_clusters_dir, f"cluster{human_cluster}")
        ensure_dir(cdir)

        build_markov_graph(
            user_label=f"Cluster {human_cluster}",
            edges_df=cluster_edges,
            event_freq=cluster_freq,
            output_path=os.path.join(cdir, "cluster_avg_session.png"),
            title_suffix=f"Z-filtered Avg Session • {category_label}",
            teams_in_cluster=teams,
            config=config,
            idf_map=idf_map or {},
            n_teams=n_teams,
        )


def main():
    parser = argparse.ArgumentParser(description="Generate Markov graphs from process model data.")
    parser.add_argument("--orientation", choices=["horizontal", "vertical"], default="horizontal",
                        help="Graph layout orientation (default: horizontal)")
    parser.add_argument("--size", type=str, default=None,
                        help="Graphviz size string (e.g. '8,5')")
    parser.add_argument("--min-edge-prob", type=float, default=0.0,
                        help="Minimum edge probability to draw (visual pruning), default: 0.0")
    parser.add_argument("--z-min", type=float, default=None,
                        help="TODO: deprecated — ignored. Use --score-min instead.")
    parser.add_argument("--score-min", type=float, default=None,
                        help="Minimum IDF distinctiveness score to keep an edge (default: off; top-K only)")
    parser.add_argument("--top-k", type=int, default=None,
                        help="Always keep top-K outgoing edges per node (default: 2 vertical, 1 horizontal)")
    parser.add_argument("--no-preserve-connectivity", dest="preserve_connectivity",
                        action="store_false", default=True,
                        help="Disable connectivity repair (Pass 2 + 3)")

    args = parser.parse_args()
    if args.z_min is not None:
        print("[WARN] --z-min is deprecated and ignored. Use --score-min instead.")

    # Process both datasets
    for dataset_name, cfg in CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"Processing: {dataset_name}")
        print(f"{'='*70}")
        
        pr_out_dir = cfg["output_folder"]
        category_label = cfg["category_label"]
        
        in_overall_fp = os.path.join(pr_out_dir, "team_transition_edges_overall.csv")
        in_avg_fp = os.path.join(pr_out_dir, "team_transition_edges_avg_session.csv")
        in_freq_fp = os.path.join(pr_out_dir, "team_event_frequency.csv")
        in_sess_fp = os.path.join(pr_out_dir, "team_transition_sessions_count.csv")
        in_cluster_fp = os.path.join(pr_out_dir, f"behavior_clusters_{category_label}.csv")
        in_zfilt_fp = os.path.join(pr_out_dir, f"team_transition_edges_avg_session_zfiltered_{category_label}.csv")
        
        # Check required files
        required_files = [in_overall_fp, in_avg_fp, in_freq_fp, in_sess_fp, in_cluster_fp, in_zfilt_fp]
        missing = [f for f in required_files if not os.path.exists(f)]
        if missing:
            print(f"[SKIP] Missing required files:")
            for f in missing:
                print(f"       - {f}")
            print(f"       Run clustering.py first")
            continue
        
        print(f"[INFO] Loading data...")
        overall_df = pd.read_csv(in_overall_fp, low_memory=False)
        avg_df = pd.read_csv(in_avg_fp, low_memory=False)
        zfilt_df = pd.read_csv(in_zfilt_fp, low_memory=False)

        # normalize team_number to string
        for df in [overall_df, avg_df, zfilt_df]:
            required = {"team_number", "from", "to", "count"}
            missing_cols = required - set(df.columns)
            if missing_cols:
                print(f"[ERROR] Missing columns: {missing_cols}")
                break
            df["team_number"] = df["team_number"].apply(_as_str_team)
            df["from"] = df["from"].astype(str)
            df["to"] = df["to"].astype(str)
            df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

        freq_map = load_event_freq_map(in_freq_fp)
        sess_count = load_sessions_count_map(in_sess_fp)
        
        # Setup output directories scoped by dataset (pr or branching)
        out_base_dir = os.path.join(ROOT, "data", "outputs", category_label)
        ensure_dir(out_base_dir)
        out_teams_dir = out_base_dir
        out_clusters_dir = os.path.join(out_base_dir, "clusters")

        # Compute IDF maps ONCE from team-level data before any per-team rendering.
        # Clusters reuse overall_idf so overlap is measured against the full population.
        print(f"[INFO] Computing cross-team IDF maps...")
        n_teams = int(overall_df["team_number"].nunique())
        overall_idf, _ = build_edge_idf_map(overall_df)
        avg_idf,     _ = build_edge_idf_map(avg_df)
        print(f"[INFO] IDF computed over {n_teams} team(s); {len(overall_idf)} overall edges, {len(avg_idf)} avg edges.")

        print(f"[INFO] Rendering team graphs...")
        render_team_graphs(overall_df, avg_df, freq_map, out_teams_dir, category_label,
                           config=args, overall_idf=overall_idf, avg_idf=avg_idf, n_teams=n_teams)

        print(f"[INFO] Rendering cluster graphs...")
        render_cluster_graphs(zfilt_df, freq_map, sess_count, in_cluster_fp, out_clusters_dir,
                              category_label, config=args, idf_map=overall_idf, n_teams=n_teams)

        print(f"[✅ OK] Graphs written to: {out_base_dir}")


if __name__ == "__main__":
    main()