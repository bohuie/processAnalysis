import os
from pathlib import Path
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph
from dotenv import load_dotenv
from src.utils.markov_common import ensure_dir, as_str_team as _as_str_team, build_markov_graph

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

OUT_TEAMS_DIR = PR_OUT_DIR
OUT_CLUSTERS_DIR = os.path.join(PR_OUT_DIR, "clusters")


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


# ---------- Team graphs ----------
def render_team_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict):
    teams = sorted(set(overall_df["team_number"]).union(set(avg_df["team_number"])),
                   key=lambda x: int(x) if str(x).isdigit() else 999999)

    for team in teams:
        team_str = _as_str_team(team)
        team_dir = os.path.join(OUT_TEAMS_DIR, f"year-long-project-team-{team_str}")
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
            title_suffix=f"Overall • {CATEGORY_LABEL}",
        )

        # Avg session (START/END expected)
        t_avg = avg_df[avg_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"team{team_str}_avg_session.png"),
            title_suffix=f"Avg Session • {CATEGORY_LABEL}",
        )


# ---------- Cluster graphs (optional) ----------
def _aggregate_cluster_avg_edges(avg_df: pd.DataFrame, teams: list[str], sess_count: dict) -> pd.DataFrame:
    """
    Session-weighted cluster avg edges:
      cluster_total_counts = sum(team_avg_count * team_num_sessions)
      cluster_avg = cluster_total_counts / sum(team_num_sessions)
    """
    total_weight = 0
    acc = {}

    for t in teams:
        w = int(sess_count.get(t, 0))
        if w <= 0:
            # fallback: treat as 1 so the team still contributes
            w = 1
        total_weight += w

        sub = avg_df[avg_df["team_number"] == t]
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


def render_cluster_graphs(avg_df: pd.DataFrame, freq_map: dict, sess_count: dict):
    if not os.path.exists(IN_CLUSTER_FP):
        print(f"[INFO] No cluster CSV found at {IN_CLUSTER_FP} — skipping cluster graphs.")
        return

    cdf = pd.read_csv(IN_CLUSTER_FP, low_memory=False)
    required = {"team_number", "cluster_id"}
    if not required.issubset(cdf.columns):
        print("[WARN] Cluster CSV missing required columns — skipping cluster graphs.")
        return

    cdf = cdf.copy()
    cdf["team_number"] = cdf["team_number"].apply(_as_str_team)
    cdf["cluster_id"] = pd.to_numeric(cdf["cluster_id"], errors="coerce").fillna(0).astype(int)

    ensure_dir(OUT_CLUSTERS_DIR)

    for cluster_id, g in cdf.groupby("cluster_id"):
        teams = sorted(g["team_number"].tolist(), key=lambda x: int(x) if x.isdigit() else 999999)

        cluster_edges = _aggregate_cluster_avg_edges(avg_df, teams, sess_count)
        cluster_freq = _aggregate_cluster_event_freq(freq_map, teams)

        # match old naming style: cluster1, cluster2, ...
        human_cluster = int(cluster_id) + 1
        cdir = os.path.join(OUT_CLUSTERS_DIR, f"cluster{human_cluster}")
        ensure_dir(cdir)

        build_markov_graph(
            user_label=f"Cluster {human_cluster}",
            edges_df=cluster_edges,
            event_freq=cluster_freq,
            output_path=os.path.join(cdir, "cluster_avg_session.png"),
            title_suffix=f"Avg Session • {CATEGORY_LABEL}",
        )


def main():
    print(f"\n[INFO] Looking for input files in: {PR_OUT_DIR}")
    
    for fp in [IN_OVERALL_FP, IN_AVG_FP]:
        if not os.path.exists(fp):
            raise FileNotFoundError(
                f"Missing required input: {fp}\n"
                f"Run transition_matrix.py first with FILE_SOURCE='{FOLDER_SOURCE}'"
            )

    overall_df = pd.read_csv(IN_OVERALL_FP, low_memory=False)
    avg_df = pd.read_csv(IN_AVG_FP, low_memory=False)

    # normalize team_number to string
    for df in [overall_df, avg_df]:
        required = {"team_number", "from", "to", "count"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in input CSV: {missing}")
        df["team_number"] = df["team_number"].apply(_as_str_team)
        df["from"] = df["from"].astype(str)
        df["to"] = df["to"].astype(str)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

    freq_map = load_event_freq_map(IN_FREQ_FP)
    sess_count = load_sessions_count_map(IN_SESS_FP)

    render_team_graphs(overall_df, avg_df, freq_map)
    render_cluster_graphs(avg_df, freq_map, sess_count)

    print(f"\n[DONE] Graphs written under: {PR_OUT_DIR}")


if __name__ == "__main__":
    main()