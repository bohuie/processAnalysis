# ============================================================
# graphing.py — PR Markov Graph Visualizer (CSV -> PNG only)
# ============================================================

import os
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

<<<<<<< HEAD
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
=======
# Determine input/output paths based on FOLDER_SOURCE
if FOLDER_SOURCE == "branching":
    PR_OUT_DIR = os.path.join(ROOT, "data", "outputs", "branching")
    CATEGORY_LABEL = "branching"
    print("[CONFIG] Processing branching graphs from data/outputs/branching/")
elif FOLDER_SOURCE == "pr":
    PR_OUT_DIR = os.path.join(ROOT, "data", "outputs", "pr")
    CATEGORY_LABEL = "pr"
    print("[CONFIG] Processing PR graphs from data/outputs/pr/")
else:
    raise ValueError(f"Invalid FOLDER_SOURCE: {FOLDER_SOURCE}. Must be 'branching' or 'pr'")

IN_OVERALL_FP = os.path.join(PR_OUT_DIR, "team_transition_edges_overall.csv")
IN_AVG_FP = os.path.join(PR_OUT_DIR, "team_transition_edges_avg_session.csv")
IN_FREQ_FP = os.path.join(PR_OUT_DIR, "team_event_frequency.csv")
IN_SESS_FP = os.path.join(PR_OUT_DIR, "team_transition_sessions_count.csv")
IN_CLUSTER_FP = os.path.join(PR_OUT_DIR, f"behavior_clusters_{FOLDER_SOURCE}.csv")
IN_ZFILT_FP = os.path.join(PR_OUT_DIR, f"team_transition_edges_avg_session_zfiltered_{FOLDER_SOURCE}.csv")

OUT_TEAMS_DIR = PR_OUT_DIR
OUT_CLUSTERS_DIR = os.path.join(PR_OUT_DIR, "clusters")

>>>>>>> origin/dev

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


# ---------- Rendering (same styling as old script) ----------
def build_markov_graph(user_label, edges_df, event_freq, output_path,
                       title_suffix="", normalize_probs=True,
                       teams_in_cluster=None):
    edges_df = edges_df.copy()
    edges_df = edges_df[edges_df["count"] > 0]
    if edges_df.empty:
        print(f"[WARN] Skipping {user_label} — no edges.")
        return

    # Build directed graph with weights
    G = nx.DiGraph()
    for _, row in edges_df.iterrows():
        a, b, w = row["from"], row["to"], float(row["count"])
        if G.has_edge(a, b):
            G[a][b]["weight"] += w
        else:
            G.add_edge(a, b, weight=w)

    # Probabilities
    for u, v in G.edges():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        G[u][v]["prob"] = G[u][v]["weight"] / total if normalize_probs and total else 0

    # Draw
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
        p = data.get("prob", 0.0)
        color = "#0D47A1" if p > 0.4 else "#1565C0" if p > 0.2 else "#64B5F6"
        dot.edge(str(u), str(v), label=f"{p:.2f}", color=color, penwidth=str(1.2 + p * 5))

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
def render_team_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict, out_teams_dir: str, category_label: str):
    teams = sorted(set(overall_df["team_number"]).union(set(avg_df["team_number"])),
                   key=lambda x: int(x) if str(x).isdigit() else 999999)

    for team in teams:
        team_str = _as_str_team(team)
        team_dir = os.path.join(out_teams_dir, f"year-long-project-team-{team_str}")
        out_overall_dir = os.path.join(team_dir, "team_overall")
        out_avg_dir = os.path.join(team_dir, "team_avg_session")
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
        )

        # Avg session (START/END expected)
        t_avg = avg_df[avg_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"team{team_str}_avg_session.png"),
            title_suffix=f"Avg Session • {category_label}",
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


<<<<<<< HEAD
def render_cluster_graphs(avg_df: pd.DataFrame, freq_map: dict, sess_count: dict, in_cluster_fp: str, out_clusters_dir: str, category_label: str):
    if not os.path.exists(in_cluster_fp):
        print(f"[INFO] No cluster CSV found at {in_cluster_fp} — skipping cluster graphs.")
=======
def render_cluster_graphs(zfilt_df: pd.DataFrame, freq_map: dict, sess_count: dict):
    if not os.path.exists(IN_CLUSTER_FP):
        print(f"[INFO] No cluster CSV found at {IN_CLUSTER_FP} — skipping cluster graphs.")
>>>>>>> origin/dev
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
<<<<<<< HEAD
            title_suffix=f"Avg Session • {category_label}",
=======
            title_suffix=f"Z-filtered Avg Session • {CATEGORY_LABEL}",
            teams_in_cluster=teams,
>>>>>>> origin/dev
        )



def main():
<<<<<<< HEAD
    # Process both datasets
    for dataset_name, config in CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"Processing: {dataset_name}")
        print(f"{'='*70}")
        
        pr_out_dir = config["output_folder"]
        category_label = config["category_label"]
        
        in_overall_fp = os.path.join(pr_out_dir, "team_transition_edges_overall.csv")
        in_avg_fp = os.path.join(pr_out_dir, "team_transition_edges_avg_session.csv")
        in_freq_fp = os.path.join(pr_out_dir, "team_event_frequency.csv")
        in_sess_fp = os.path.join(pr_out_dir, "team_transition_sessions_count.csv")
        in_cluster_fp = os.path.join(pr_out_dir, f"behavior_clusters_{category_label}.csv")
        
        # Check required files
        required_files = [in_overall_fp, in_avg_fp, in_freq_fp, in_sess_fp, in_cluster_fp]
        missing = [f for f in required_files if not os.path.exists(f)]
=======
    print(f"\n[INFO] Looking for input files in: {PR_OUT_DIR}")
    
    for fp in [IN_OVERALL_FP, IN_AVG_FP]:
        if not os.path.exists(fp):
            raise FileNotFoundError(
                f"Missing required input: {fp}\n"
                f"Run transition_matrix.py first with FILE_SOURCE='{FOLDER_SOURCE}'"
            )

    overall_df = pd.read_csv(IN_OVERALL_FP, low_memory=False)
    avg_df = pd.read_csv(IN_AVG_FP, low_memory=False)
    
    if not os.path.exists(IN_ZFILT_FP):
        raise FileNotFoundError(
            f"Missing required input: {IN_ZFILT_FP}\n"
            f"Run clustering.py first to generate the z-filtered edges export."
        )

    zfilt_df = pd.read_csv(IN_ZFILT_FP, low_memory=False)

    # normalize like the others
    required = {"team_number", "from", "to", "count"}
    missing = required - set(zfilt_df.columns)
    if missing:
        raise ValueError(f"Missing columns in z-filtered edges CSV: {missing}")

    zfilt_df["team_number"] = zfilt_df["team_number"].apply(_as_str_team)
    zfilt_df["from"] = zfilt_df["from"].astype(str)
    zfilt_df["to"] = zfilt_df["to"].astype(str)
    zfilt_df["count"] = pd.to_numeric(zfilt_df["count"], errors="coerce").fillna(0.0).astype(float)


    # normalize team_number to string
    for df in [overall_df, avg_df]:
        required = {"team_number", "from", "to", "count"}
        missing = required - set(df.columns)
>>>>>>> origin/dev
        if missing:
            print(f"[SKIP] Missing required files:")
            for f in missing:
                print(f"       - {f}")
            print(f"       Run clustering.py first")
            continue
        
        print(f"[INFO] Loading data...")
        overall_df = pd.read_csv(in_overall_fp, low_memory=False)
        avg_df = pd.read_csv(in_avg_fp, low_memory=False)

        # normalize team_number to string
        for df in [overall_df, avg_df]:
            required = {"team_number", "from", "to", "count"}
            missing_cols = required - set(df.columns)
            if missing_cols:
                print(f"[ERROR] Missing columns: {missing_cols}")
                break
            df["team_number"] = df["team_number"].apply(_as_str_team)
            df["from"] = df["from"].astype(str)
            df["to"] = df["to"].astype(str)
            df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

<<<<<<< HEAD
        freq_map = load_event_freq_map(in_freq_fp)
        sess_count = load_sessions_count_map(in_sess_fp)
        
        # Setup output directories scoped by dataset (pr or branching)
        out_base_dir = os.path.join(ROOT, "data", "outputs", category_label)
        ensure_dir(out_base_dir)
        out_teams_dir = out_base_dir
        out_clusters_dir = os.path.join(out_base_dir, "clusters")
=======
    render_team_graphs(overall_df, avg_df, freq_map)
    render_cluster_graphs(zfilt_df, freq_map, sess_count)

>>>>>>> origin/dev

        print(f"[INFO] Rendering team graphs...")
        render_team_graphs(overall_df, avg_df, freq_map, out_teams_dir, category_label)
        
        print(f"[INFO] Rendering cluster graphs...")
        render_cluster_graphs(avg_df, freq_map, sess_count, in_cluster_fp, out_clusters_dir, category_label)

        print(f"[✅ OK] Graphs written to: {out_base_dir}")


if __name__ == "__main__":
    main()