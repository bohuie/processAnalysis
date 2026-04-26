import os
import re
import glob
import pandas as pd

from src.utils.markov_common import (
    explode_and_sort_events,
    compute_overall_edges,
    compute_avg_session_edges,
    add_transition_probs,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION - Process ALL datasets every run (no env toggles)
# ============================================================

CONFIGS = {
    "branching": {
        "data_folder": os.path.join(ROOT, "data", "graph_labels", "clean"),
        "prefix": "CLEAN_year-long-project-team-",
        "pattern": "*_labels_branching_and_structure.csv",
        "regex": re.compile(
            r"^CLEAN_(year-long-project-team-\d+)_labels_branching_and_structure\.csv$",
            re.IGNORECASE,
        ),
        "example": "CLEAN_year-long-project-team-7_labels_branching_and_structure.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "branching"),
    },
    "pr": {
        "data_folder": os.path.join(ROOT, "data", "csv"),
        "prefix": "CLEAN_pr_labels_",
        "pattern": "year-long-project-team-*.csv",
        "regex": re.compile(
            r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$",
            re.IGNORECASE,
        ),
        "example": "CLEAN_pr_labels_year-long-project-team-7.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "pr"),
    },
    "communication": {
        "data_folder": os.path.join(ROOT, "data", "csv"),
        "prefix": "CLEAN_communication_labels_",
        "pattern": "year-long-project-team-*.csv",
        "regex": re.compile(
            r"^CLEAN_communication_labels_(year-long-project-team-\d+)\.csv$",
            re.IGNORECASE,
        ),
        "example": "CLEAN_communication_labels_year-long-project-team-7.csv",
        "output_folder": os.path.join(ROOT, "data", "outputs", "communication"),
    },
}


# ============================================================
# HELPERS
# ============================================================

def discover_clean_team_files(config: dict) -> list[str]:
    data_folder = config["data_folder"]
    search_pattern = os.path.join(data_folder, f"{config['prefix']}{config['pattern']}")
    files = sorted(set(glob.glob(search_pattern)))
    if not files:
        raise FileNotFoundError(
            f"No CLEAN label CSVs found in {data_folder}\n"
            f"Expected e.g.: {os.path.join(data_folder, config['example'])}"
        )
    return files


def parse_team_name_and_number(fp: str, config: dict) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = config["regex"].match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def load_noholes_csv(fp: str) -> pd.DataFrame:
    df = pd.read_csv(fp, low_memory=False)
    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")
    return explode_and_sort_events(df)


# ============================================================
# MAIN
# ============================================================

def process_dataset(dataset_name: str, config: dict) -> None:
    print(f"\n{'='*70}")
    print(f"Processing: {dataset_name}")
    print(f"{'='*70}")

    out_folder = config["output_folder"]
    os.makedirs(out_folder, exist_ok=True)

    try:
        files = discover_clean_team_files(config)
    except FileNotFoundError as e:
        print(f"[SKIP] {e}")
        return

    print(f"[INFO] Found {len(files)} CLEAN team file(s). Output -> {out_folder}")

    all_overall, all_avg, all_freq, sessions_rows = [], [], [], []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp, config)

        try:
            df = load_noholes_csv(fp)
        except Exception as e:
            print(f"[WARN] Skipping {os.path.basename(fp)}: {e}")
            continue

        # event frequency
        freq = df["event"].value_counts().reset_index()
        freq.columns = ["event", "count"]
        freq.insert(0, "team_number", team_number)
        freq.insert(0, "team_name", team_name)
        all_freq.append(freq)

        overall_edges, n_sessions = compute_overall_edges(df)
        avg_edges = compute_avg_session_edges(df, n_sessions=n_sessions)

        overall_edges = add_transition_probs(overall_edges)
        avg_edges = add_transition_probs(avg_edges)

        for df_out in (overall_edges, avg_edges):
            df_out.insert(0, "team_name", team_name)
            df_out.insert(1, "team_number", team_number)

        all_overall.append(overall_edges)
        all_avg.append(avg_edges)

        sessions_rows.append(
            {"team_name": team_name, "team_number": team_number, "num_pr_sessions": int(n_sessions)}
        )

    if not all_overall:
        print(f"[WARN] No usable data produced for {dataset_name}")
        return

    pd.concat(all_overall, ignore_index=True).to_csv(
        os.path.join(out_folder, "team_transition_edges_overall.csv"), index=False
    )
    pd.concat(all_avg, ignore_index=True).to_csv(
        os.path.join(out_folder, "team_transition_edges_avg_session.csv"), index=False
    )
    pd.DataFrame(sessions_rows).to_csv(
        os.path.join(out_folder, "team_transition_sessions_count.csv"), index=False
    )
    pd.concat(all_freq, ignore_index=True).to_csv(
        os.path.join(out_folder, "team_event_frequency.csv"), index=False
    )

    print(f"[OK] Wrote transition CSVs for {dataset_name} -> {out_folder}")


def main():
    for dataset_name, config in CONFIGS.items():
        process_dataset(dataset_name, config)


if __name__ == "__main__":
    main()