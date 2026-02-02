# ============================================================
# graphing_individual.py — Individual PR Markov Graph Visualizer
# Reads individual_* CSVs and renders per-user PNGs
# ============================================================

import os
import re
from pathlib import Path
import pandas as pd
import numpy as np
import networkx as nx
from graphviz import Digraph
from dotenv import load_dotenv

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


# ---------- Tiny utils ----------
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _as_str_team(x) -> str:
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


# ---------- Rendering ----------
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

    print(f"\n[✅ DONE] Individual graphs written under: {OUT_USERS_ROOT}")


if __name__ == "__main__":
    main()