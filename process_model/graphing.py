# process_model/graphing.py

import os
import pandas as pd
import numpy as np

from src.utils.markov_common import ensure_dir, as_str_team as _as_str_team, build_markov_graph

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

CONFIGS = {
    "branching": {"output_folder": os.path.join(ROOT, "data", "outputs", "branching"), "category_label": "branching"},
    "pr": {"output_folder": os.path.join(ROOT, "data", "outputs", "pr"), "category_label": "pr"},
    "communication": {"output_folder": os.path.join(ROOT, "data", "outputs", "communication"), "category_label": "communication"},
}


def load_event_freq_map(freq_fp: str) -> dict:
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


def render_team_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict, out_teams_dir: str, category_label: str):
    teams = sorted(
        set(overall_df["team_number"]).union(set(avg_df["team_number"])),
        key=lambda x: int(x) if str(x).isdigit() else 999999,
    )

    for team in teams:
        team_str = _as_str_team(team)
        team_dir = os.path.join(out_teams_dir, f"year-long-project-team-{team_str}")
        out_overall_dir = os.path.join(team_dir, "team_overall")
        out_avg_dir = os.path.join(team_dir, "team_avg_session")
        ensure_dir(out_overall_dir)
        ensure_dir(out_avg_dir)

        event_freq = freq_map.get(team_str, {})

        t_overall = overall_df[overall_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_overall,
            event_freq=event_freq,
            output_path=os.path.join(out_overall_dir, f"team{team_str}_overall.png"),
            title_suffix=f"Overall • {category_label}",
        )

        t_avg = avg_df[avg_df["team_number"] == team_str][["from", "to", "count"]].copy()
        build_markov_graph(
            user_label=f"Team {team_str}",
            edges_df=t_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"team{team_str}_avg_session.png"),
            title_suffix=f"Avg Session • {category_label}",
        )


def _aggregate_cluster_avg_edges(avg_df: pd.DataFrame, teams: list[str], sess_count: dict) -> pd.DataFrame:
    total_weight = 0
    acc = {}

    for t in teams:
        w = int(sess_count.get(t, 0))
        if w <= 0:
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


def render_cluster_graphs(avg_df: pd.DataFrame, freq_map: dict, sess_count: dict, cluster_fp: str, out_clusters_dir: str, category_label: str):
    if not os.path.exists(cluster_fp):
        print(f"[INFO] No cluster CSV found at {cluster_fp} — skipping cluster graphs.")
        return

    cdf = pd.read_csv(cluster_fp, low_memory=False)
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
        cluster_edges = _aggregate_cluster_avg_edges(avg_df, teams, sess_count)
        cluster_freq = _aggregate_cluster_event_freq(freq_map, teams)

        human_cluster = int(cluster_id) + 1
        cdir = os.path.join(out_clusters_dir, f"cluster{human_cluster}")
        ensure_dir(cdir)

        build_markov_graph(
            user_label=f"Cluster {human_cluster}",
            edges_df=cluster_edges,
            event_freq=cluster_freq,
            output_path=os.path.join(cdir, "cluster_avg_session.png"),
            title_suffix=f"Avg Session • {category_label}",
        )


def process_dataset(dataset_name: str, output_folder: str, category_label: str) -> None:
    print(f"\n{'='*70}")
    print(f"Processing: {dataset_name}")
    print(f"{'='*70}")

    in_overall_fp = os.path.join(output_folder, "team_transition_edges_overall.csv")
    in_avg_fp = os.path.join(output_folder, "team_transition_edges_avg_session.csv")
    in_freq_fp = os.path.join(output_folder, "team_event_frequency.csv")
    in_sess_fp = os.path.join(output_folder, "team_transition_sessions_count.csv")
    in_cluster_fp = os.path.join(output_folder, f"behavior_clusters_{category_label}.csv")

    required = [in_overall_fp, in_avg_fp, in_freq_fp, in_sess_fp]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        print("[SKIP] Missing required inputs:")
        for p in missing:
            print(f"       - {p}")
        print("       Run transition_edges.py first.")
        return

    overall_df = pd.read_csv(in_overall_fp, low_memory=False)
    avg_df = pd.read_csv(in_avg_fp, low_memory=False)

    for df in [overall_df, avg_df]:
        req_cols = {"team_number", "from", "to", "count"}
        miss = req_cols - set(df.columns)
        if miss:
            raise ValueError(f"Missing columns in input CSV: {miss}")
        df["team_number"] = df["team_number"].apply(_as_str_team)
        df["from"] = df["from"].astype(str)
        df["to"] = df["to"].astype(str)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

    freq_map = load_event_freq_map(in_freq_fp)
    sess_count = load_sessions_count_map(in_sess_fp)

    out_clusters_dir = os.path.join(output_folder, "clusters")
    ensure_dir(output_folder)

    print("[INFO] Rendering team graphs...")
    render_team_graphs(overall_df, avg_df, freq_map, output_folder, category_label)

    print("[INFO] Rendering cluster graphs...")
    render_cluster_graphs(avg_df, freq_map, sess_count, in_cluster_fp, out_clusters_dir, category_label)

    print(f"[✅ OK] Graphs written to: {output_folder}")


def main():
    for dataset_name, cfg in CONFIGS.items():
        process_dataset(dataset_name, cfg["output_folder"], cfg["category_label"])


if __name__ == "__main__":
    main()