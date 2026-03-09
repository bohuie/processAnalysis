# process_model/graphing_individual.py

import os
import pandas as pd

from src.utils.markov_common import ensure_dir, as_str_team as _as_str_team, slugify_user, build_markov_graph

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

CONFIGS = {
    "branching": {
        "out_dir": os.path.join(ROOT, "data", "outputs", "branching_individual"),
        "category_label": "branching",
    },
    "pr": {
        "out_dir": os.path.join(ROOT, "data", "outputs", "pr_individual"),
        "category_label": "pr",
    },
    "communication": {
        "out_dir": os.path.join(ROOT, "data", "outputs", "communication_individual"),
        "category_label": "communication",
    },
}


def load_event_freq_map(freq_fp: str) -> dict:
    """
    Returns: {(team_number_str, user_str): {event: count_int}}
    """
    if not os.path.exists(freq_fp):
        return {}
    df = pd.read_csv(freq_fp, low_memory=False)
    required = {"team_number", "user", "event", "count"}
    if not required.issubset(df.columns):
        return {}

    df = df.copy()
    df["team_number"] = df["team_number"].apply(_as_str_team)
    df["user"] = df["user"].astype(str).str.strip()
    df["event"] = df["event"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)

    out = {}
    for (team, user), g in df.groupby(["team_number", "user"]):
        out[(team, user)] = dict(zip(g["event"], g["count"]))
    return out


def render_user_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict, out_users_root: str, category_label: str):
    pairs = sorted(
        set(zip(overall_df["team_number"], overall_df["user"])) | set(zip(avg_df["team_number"], avg_df["user"])),
        key=lambda x: (int(x[0]) if str(x[0]).isdigit() else 999999, x[1].lower()),
    )

    for team, user in pairs:
        team_str = _as_str_team(team)
        user_str = str(user).strip()
        user_slug = slugify_user(user_str)

        base_dir = os.path.join(out_users_root, f"year-long-project-team-{team_str}", user_slug)
        out_overall_dir = os.path.join(base_dir, "individual_overall")
        out_avg_dir = os.path.join(base_dir, "individual_avg_session")
        ensure_dir(out_overall_dir)
        ensure_dir(out_avg_dir)

        event_freq = freq_map.get((team_str, user_str), {})

        u_overall = overall_df[
            (overall_df["team_number"] == team_str) & (overall_df["user"] == user_str)
        ][["from", "to", "count"]].copy()

        build_markov_graph(
            user_label=f"{user_str} • Team {team_str}",
            edges_df=u_overall,
            event_freq=event_freq,
            output_path=os.path.join(out_overall_dir, f"{user_slug}_overall.png"),
            title_suffix=f"Overall • {category_label}",
        )

        u_avg = avg_df[
            (avg_df["team_number"] == team_str) & (avg_df["user"] == user_str)
        ][["from", "to", "count"]].copy()

        build_markov_graph(
            user_label=f"{user_str} • Team {team_str}",
            edges_df=u_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"{user_slug}_avg_session.png"),
            title_suffix=f"Avg Session • {category_label}",
        )


def process_dataset(dataset_name: str, out_dir: str, category_label: str) -> None:
    print(f"\n{'='*70}")
    print(f"Processing individual graphs: {dataset_name}")
    print(f"{'='*70}")

    in_overall_fp = os.path.join(out_dir, "individual_transition_edges_overall.csv")
    in_avg_fp = os.path.join(out_dir, "individual_transition_edges_avg_session.csv")
    in_freq_fp = os.path.join(out_dir, "individual_event_frequency.csv")

    required = [in_overall_fp, in_avg_fp, in_freq_fp]
    missing = [p for p in required if not os.path.exists(p)]
    if missing:
        print("[SKIP] Missing required inputs:")
        for p in missing:
            print(f"       - {p}")
        print("       Run transition_edges_individual.py first.")
        return

    overall_df = pd.read_csv(in_overall_fp, low_memory=False)
    avg_df = pd.read_csv(in_avg_fp, low_memory=False)

    for df in [overall_df, avg_df]:
        required_cols = {"team_number", "user", "from", "to", "count"}
        miss = required_cols - set(df.columns)
        if miss:
            raise ValueError(f"Missing columns in input CSV: {miss}")
        df["team_number"] = df["team_number"].apply(_as_str_team)
        df["user"] = df["user"].astype(str).str.strip()
        df["from"] = df["from"].astype(str)
        df["to"] = df["to"].astype(str)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

    freq_map = load_event_freq_map(in_freq_fp)

    out_users_root = os.path.join(out_dir, "users")
    ensure_dir(out_users_root)

    render_user_graphs(overall_df, avg_df, freq_map, out_users_root, category_label)

    print(f"[DONE] Individual graphs written under: {out_users_root}")


def main():
    for dataset_name, cfg in CONFIGS.items():
        process_dataset(dataset_name, cfg["out_dir"], cfg["category_label"])


if __name__ == "__main__":
    main()