import os, re, glob
import pandas as pd
import numpy as np
import ast
from pathlib import Path
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))

# ============================================================
# CONFIGURATION SWITCH - Choose which files to process
# ============================================================
# FILE_SOURCE = "branching" or "pr_labels"
script_path = Path(__file__).resolve()
env_path = script_path.parent.parent / ".env"

print(f"[DEBUG] Script location: {script_path}")
print(f"[DEBUG] Looking for .env at: {env_path}")
print(f"[DEBUG] .env exists: {env_path.exists()}")

load_dotenv(dotenv_path=env_path)

FILE_SOURCE = os.getenv("FILE_SOURCE")
print(f"[DEBUG] FILE_SOURCE = {FILE_SOURCE}")

# ----------------------------
# Configs
# ----------------------------
BRANCHING_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "graph_labels"),
    "pattern": "*_labels_branching_and_structure.csv",
    # supports both CLEAN_ and non-clean
    "regex": re.compile(
        r"^(?:CLEAN_)?(year-long-project-team-\d+)_labels_branching_and_structure\.csv$",
        re.IGNORECASE,
    ),
    "example": "year-long-project-team-15_labels_branching_and_structure.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "branching_individual"),
}

PR_LABELS_CONFIG = {
    "data_folder": os.path.join(ROOT, "data", "csv"),
    # supports both "pr_labels_year-long-project-team-15.csv" and "CLEAN_pr_labels_year-long-project-team-15.csv"
    "pattern": "*year-long-project-team-*.csv",
    "regex": re.compile(
        r"^(?:CLEAN_)?(?:pr_labels_)?(year-long-project-team-\d+)\.csv$",
        re.IGNORECASE,
    ),
    "example": "pr_labels_year-long-project-team-15.csv",
    "output_folder": os.path.join(ROOT, "data", "outputs", "pr_individual"),
}

if FILE_SOURCE == "branching":
    CONFIG = BRANCHING_CONFIG
    print("[CONFIG] Using branching_and_structure files (individual split by pr_author)")
elif FILE_SOURCE == "pr_labels":
    CONFIG = PR_LABELS_CONFIG
    print("[CONFIG] Using pr_labels files (individual split by derived user column)")
else:
    raise ValueError(f"Invalid FILE_SOURCE: {FILE_SOURCE}. Must be 'branching' or 'pr_labels'")

DATA_FOLDER = CONFIG["data_folder"]
TEAM_RE = CONFIG["regex"]
OUT_FOLDER = CONFIG["output_folder"]
os.makedirs(OUT_FOLDER, exist_ok=True)


# ============================================================
# Helpers
# ============================================================
def discover_team_files() -> list[str]:
    search_pattern = os.path.join(DATA_FOLDER, CONFIG["pattern"])
    hits = glob.glob(search_pattern)
    files = sorted(set(hits))
    if not files:
        raise FileNotFoundError(
            f"No label CSVs found in {DATA_FOLDER}\n"
            f"Expected e.g.: {os.path.join(DATA_FOLDER, CONFIG['example'])}"
        )
    return files


def parse_team_name_and_number(fp: str) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = TEAM_RE.match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number


def normalize_event_field(event):
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


def _norm_user(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def derive_user_column_for_pr_labels(df: pd.DataFrame) -> pd.Series:
    """
    Rule:
      - look at `source` first
      - if empty OR "pr" => user = pr_author
      - else if "review" => user = author
      - else fallback: pr_author then author
    """
    src = df.get("source")
    pr_author = df.get("pr_author")
    author = df.get("author")

    if src is None:
        src = pd.Series([""] * len(df), index=df.index)
    if pr_author is None:
        pr_author = pd.Series([""] * len(df), index=df.index)
    if author is None:
        author = pd.Series([""] * len(df), index=df.index)

    src_norm = src.astype(str).str.strip().str.lower().replace({"nan": ""})
    pr_author_norm = pr_author.astype(str).str.strip().replace({"nan": ""})
    author_norm = author.astype(str).str.strip().replace({"nan": ""})

    user = np.where(
        (src_norm == "") | (src_norm == "pr"),
        pr_author_norm,
        np.where(src_norm == "review", author_norm, np.where(pr_author_norm != "", pr_author_norm, author_norm)),
    )

    # final cleanup
    user = pd.Series(user, index=df.index).astype(str).str.strip().replace({"nan": ""})
    return user


def load_csv_with_user(fp: str, file_source: str) -> pd.DataFrame:
    df = pd.read_csv(fp, low_memory=False)

    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["_row_idx"] = np.arange(len(df))

    # parse/explode events (same as old behavior)
    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]
    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    # user column
    if file_source == "branching":
        if "pr_author" not in df.columns:
            raise ValueError(f"{fp} missing required column for branching: pr_author")
        df["user"] = df["pr_author"].apply(_norm_user)
    else:
        df["user"] = derive_user_column_for_pr_labels(df)

    # drop empty users
    df["user"] = df["user"].astype(str).str.strip()
    df = df[df["user"].ne("")]

    return df[["pr_id", "timestamp", "event", "user"]]


def compute_overall_edges_old_style(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
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


def compute_avg_session_edges_old_style(df: pd.DataFrame, n_sessions: int) -> pd.DataFrame:
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

    avg_edges = pd.DataFrame(
        [{"from": a, "to": b, "count": c / n_sessions} for (a, b), c in edge_counter.items()]
    )
    return avg_edges


def add_transition_probs(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.assign(prob=[])
    edges = edges.copy()
    edges["count"] = edges["count"].astype(float)
    denom = edges.groupby("from")["count"].transform("sum")
    edges["prob"] = np.where(denom > 0, edges["count"] / denom, 0.0)
    return edges


# ============================================================
# Main
# ============================================================
def main():
    files = discover_team_files()
    print(f"[INFO] Found {len(files)} files:")
    for f in files:
        print(" -", f)

    all_overall, all_avg, all_freq, sessions_rows = [], [], [], []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp)
        df = load_csv_with_user(fp, FILE_SOURCE)

        # split by user (individual-level)
        for user, udf in df.groupby("user", sort=False):
            # event frequency (per user)
            freq = udf["event"].value_counts().reset_index()
            freq.columns = ["event", "count"]
            freq.insert(0, "user", user)
            freq.insert(0, "team_number", team_number)
            freq.insert(0, "team_name", team_name)
            all_freq.append(freq)

            overall_edges, n_sessions = compute_overall_edges_old_style(udf)
            avg_edges = compute_avg_session_edges_old_style(udf, n_sessions=n_sessions)

            overall_edges = add_transition_probs(overall_edges)
            avg_edges = add_transition_probs(avg_edges)

            for out_df in (overall_edges, avg_edges):
                out_df.insert(0, "user", user)
                out_df.insert(0, "team_number", team_number)
                out_df.insert(0, "team_name", team_name)

            all_overall.append(overall_edges)
            all_avg.append(avg_edges)

            sessions_rows.append(
                {
                    "team_name": team_name,
                    "team_number": team_number,
                    "user": user,
                    "num_pr_sessions": int(n_sessions),
                }
            )

    pd.concat(all_overall, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "individual_transition_edges_overall.csv"), index=False
    )
    pd.concat(all_avg, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "individual_transition_edges_avg_session.csv"), index=False
    )
    pd.DataFrame(sessions_rows).to_csv(
        os.path.join(OUT_FOLDER, "individual_transition_sessions_count.csv"), index=False
    )
    pd.concat(all_freq, ignore_index=True).to_csv(
        os.path.join(OUT_FOLDER, "individual_event_frequency.csv"), index=False
    )

    print("[OK] Wrote individual transition CSVs to:", OUT_FOLDER)


if __name__ == "__main__":
    main()