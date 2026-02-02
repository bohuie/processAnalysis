import os, re, glob
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

from src.utils.markov_common import (
    normalize_event_field,
    explode_and_sort_events,
    compute_overall_edges,
    compute_avg_session_edges,
    add_transition_probs,
)

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

    return pd.Series(user, index=df.index).astype(str).str.strip().replace({"nan": ""})


def _explode_with_row_idx(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Local explode that matches old behavior (and includes _row_idx so user stays aligned).
    """
    df = raw.copy()

    # stable row ordering key
    if "_row_idx" not in df.columns:
        df["_row_idx"] = np.arange(len(df))

    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]

    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)
    return df


def load_csv_with_user(fp: str, file_source: str) -> pd.DataFrame:
    raw = pd.read_csv(fp, low_memory=False)

    required = {"pr_id", "timestamp", "event"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    # derive user BEFORE explode
    if file_source == "branching":
        if "pr_author" not in raw.columns:
            raise ValueError(f"{fp} missing required column for branching: pr_author")
        raw["user"] = raw["pr_author"].apply(_norm_user)
    else:
        raw["user"] = derive_user_column_for_pr_labels(raw)

    raw["user"] = raw["user"].astype(str).str.strip()
    raw = raw[raw["user"].ne("")].copy()

    # keep original order key
    raw["_row_idx"] = np.arange(len(raw))

    # 1) explode events using shared helper (preferred)
    #    We try keep_row_idx=True if your common helper supports it.
    try:
        events_only = explode_and_sort_events(raw, keep_row_idx=True)  # type: ignore[arg-type]
    except TypeError:
        # common helper doesn't support keep_row_idx yet → use local explode for events
        tmp = _explode_with_row_idx(raw)
        events_only = tmp[["pr_id", "timestamp", "event", "_row_idx"]].copy()

    # 2) explode user in the EXACT same shape/order so it aligns 1:1
    raw_u = _explode_with_row_idx(raw)

    # safety: if shapes don't match (shouldn't happen), fall back to raw_u as source of truth
    if len(events_only) != len(raw_u):
        events_only = raw_u[["pr_id", "timestamp", "event", "_row_idx"]].copy()

    out = events_only.reset_index(drop=True).copy()
    out["user"] = raw_u["user"].astype(str).str.strip().fillna("").reset_index(drop=True)
    out = out[out["user"].ne("")]

    return out[["pr_id", "timestamp", "event", "user"]]


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

            overall_edges, n_sessions = compute_overall_edges(udf)
            avg_edges = compute_avg_session_edges(udf, n_sessions=n_sessions)

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
