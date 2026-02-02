import os
import re
from pathlib import Path
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph
from dotenv import load_dotenv
from src.utils.markov_common import ensure_dir, as_str_team as _as_str_team, slugify_user, build_markov_graph

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION SWITCH - Choose which folder to process
# ============================================================
# FOLDER_SOURCE = "branching" or "pr"
script_path = Path(__file__).resolve()
env_path = script_path.parent.parent / ".env"

print(f"[DEBUG] Script location: {script_path}")
print(f"[DEBUG] Looking for .env at: {env_path}")
print(f"[DEBUG] .env exists: {env_path.exists()}")

load_dotenv(dotenv_path=env_path)
FOLDER_SOURCE = os.getenv("FOLDER_SOURCE")
print(f"[DEBUG] FOLDER_SOURCE = {FOLDER_SOURCE}")

if FOLDER_SOURCE == "branching":
    OUT_DIR = os.path.join(ROOT, "data", "outputs", "branching_individual")
    CATEGORY_LABEL = "branching"
    print("[CONFIG] Processing individual branching graphs from data/outputs/branching_individual/")
elif FOLDER_SOURCE == "pr":
    OUT_DIR = os.path.join(ROOT, "data", "outputs", "pr_individual")
    CATEGORY_LABEL = "pr"
    print("[CONFIG] Processing individual PR graphs from data/outputs/pr_individual/")
else:
    raise ValueError(f"Invalid FOLDER_SOURCE: {FOLDER_SOURCE}. Must be 'branching' or 'pr'")

IN_OVERALL_FP = os.path.join(OUT_DIR, "individual_transition_edges_overall.csv")
IN_AVG_FP = os.path.join(OUT_DIR, "individual_transition_edges_avg_session.csv")
IN_FREQ_FP = os.path.join(OUT_DIR, "individual_event_frequency.csv")
IN_SESS_FP = os.path.join(OUT_DIR, "individual_transition_sessions_count.csv")

OUT_USERS_ROOT = os.path.join(OUT_DIR, "users")


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


def render_user_graphs(overall_df: pd.DataFrame, avg_df: pd.DataFrame, freq_map: dict):
    # iterate all (team, user) pairs present
    pairs = sorted(
        set(zip(overall_df["team_number"], overall_df["user"])) | set(zip(avg_df["team_number"], avg_df["user"])),
        key=lambda x: (int(x[0]) if str(x[0]).isdigit() else 999999, x[1].lower()),
    )

    for team, user in pairs:
        team_str = _as_str_team(team)
        user_str = str(user).strip()
        user_slug = slugify_user(user_str)

        base_dir = os.path.join(OUT_USERS_ROOT, f"year-long-project-team-{team_str}", user_slug)
        out_overall_dir = os.path.join(base_dir, "individual_overall")
        out_avg_dir = os.path.join(base_dir, "individual_avg_session")
        ensure_dir(out_overall_dir)
        ensure_dir(out_avg_dir)

        event_freq = freq_map.get((team_str, user_str), {})

        # Overall
        u_overall = overall_df[
            (overall_df["team_number"] == team_str) & (overall_df["user"] == user_str)
        ][["from", "to", "count"]].copy()

        build_markov_graph(
            user_label=f"{user_str} • Team {team_str}",
            edges_df=u_overall,
            event_freq=event_freq,
            output_path=os.path.join(out_overall_dir, f"{user_slug}_overall.png"),
            title_suffix=f"Overall • {CATEGORY_LABEL}",
        )

        # Avg session
        u_avg = avg_df[
            (avg_df["team_number"] == team_str) & (avg_df["user"] == user_str)
        ][["from", "to", "count"]].copy()

        build_markov_graph(
            user_label=f"{user_str} • Team {team_str}",
            edges_df=u_avg,
            event_freq=event_freq,
            output_path=os.path.join(out_avg_dir, f"{user_slug}_avg_session.png"),
            title_suffix=f"Avg Session • {CATEGORY_LABEL}",
        )


def main():
    print(f"\n[INFO] Looking for input files in: {OUT_DIR}")
    for fp in [IN_OVERALL_FP, IN_AVG_FP, IN_FREQ_FP]:
        if not os.path.exists(fp):
            raise FileNotFoundError(
                f"Missing required input: {fp}\n"
                f"Run transition_edges_individual.py first with FILE_SOURCE='{FOLDER_SOURCE}'"
            )

    overall_df = pd.read_csv(IN_OVERALL_FP, low_memory=False)
    avg_df = pd.read_csv(IN_AVG_FP, low_memory=False)

    for df in [overall_df, avg_df]:
        required = {"team_number", "user", "from", "to", "count"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in input CSV: {missing}")
        df["team_number"] = df["team_number"].apply(_as_str_team)
        df["user"] = df["user"].astype(str).str.strip()
        df["from"] = df["from"].astype(str)
        df["to"] = df["to"].astype(str)
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0.0).astype(float)

    freq_map = load_event_freq_map(IN_FREQ_FP)

    render_user_graphs(overall_df, avg_df, freq_map)

    print(f"\n[DONE] Individual graphs written under: {OUT_USERS_ROOT}")


if __name__ == "__main__":
    main()