import os
import glob
from datetime import datetime

import pandas as pd
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv

from src.utils.normalize_pr_id import normalize_pr_ids
from src.utils.label_merge import label_merge_state

from event_labelling.Communication.helpers_comm import append_event, find_file
from event_labelling.Communication.prep_data import preprocess_team_csvs
from event_labelling.Communication.llm_prompts import classify_commit_message
from event_labelling.Communication.get_clean_comm_label import create_clean_comm_label_csv


# == GLOBALS ==========================================================
PRS_PATTERN_TEMPLATES = [
    "{team}_all_pull_requests.csv",
    "{team}_PRs.csv",
    "all_pull_requests.csv",
]

COMMITS_PATTERN_TEMPLATES = [
    "{team}_PR_commits.csv",
    "{team}_commits.csv",
    "PR_commits.csv",
]

COMM_LABELS = {
    "feature_documented",
    "feature_undocumented",
    "commit_informative",
    "commit_uninformative",
    "self_merge",
    "no_merge",
    "reviewed_merge",
}


# === SETUP ============================================================
load_dotenv()

RUN_TIMESTAMP = datetime.utcnow().isoformat() + "Z"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
DATA_FOLDER = os.path.join(PROJECT_ROOT, "data", "csv")
os.makedirs(DATA_FOLDER, exist_ok=True)

CACHE_PATH = os.path.join(DATA_FOLDER, "commit_message_cache.csv")
PR_LOOKUP_PATH = os.path.join(DATA_FOLDER, "pr_timestamp_lookup.csv")


# === SMALL HELPERS (NO NESTED FUNCS) ==================================
def _load_commit_cache() -> dict[str, str]:
    if os.path.exists(CACHE_PATH):
        cache_df = pd.read_csv(CACHE_PATH)
        if {"commit_message", "event"} <= set(cache_df.columns):
            cache = dict(
                zip(
                    cache_df["commit_message"].astype(str),
                    cache_df["event"].astype(str),
                )
            )
            print(f"[INFO] Loaded {len(cache)} cached commit analyses.")
            return cache
    return {}


def _save_commit_cache(cache: dict[str, str]) -> None:
    cache_df = pd.DataFrame(
        [{"commit_message": k, "event": v} for k, v in cache.items()],
        columns=["commit_message", "event"],
    )
    cache_df.to_csv(CACHE_PATH, index=False)
    print(f"[INFO] Saved commit cache → {CACHE_PATH} ({len(cache)} rows)")


def _pick_commit_time_column(commits_df: pd.DataFrame) -> str | None:
    candidates = [
        "created_at",
        "commit_created_at",
        "commit_date",
        "commit_timestamp",
        "timestamp",
        "date",
    ]
    for c in candidates:
        if c in commits_df.columns:
            return c
    return None


def _evs_to_list(ev) -> list[str]:
    """Normalize event cell to list[str]."""
    if isinstance(ev, list):
        return [e for e in ev if isinstance(e, str)]
    if isinstance(ev, str):
        return [ev]
    return []


def _keep_comm_events(ev) -> list[str]:
    """Keep only Communication labels from an event cell."""
    evs = _evs_to_list(ev)
    return [e for e in evs if e in COMM_LABELS]


def _apply_default_uninformative(commits_df: pd.DataFrame) -> pd.DataFrame:
    """If commit_message missing, set all rows to commit_uninformative."""
    commits_df = commits_df.copy()
    commits_df["event"] = commits_df["event"].apply(
        lambda ev: append_event(ev, "commit_uninformative")
    )
    return commits_df


def _label_commit_informativeness(
    commits_df: pd.DataFrame,
    cache: dict[str, str],
) -> pd.DataFrame:
    """Add commit_informative / commit_uninformative labels to commits_df using cache."""
    commits_df = commits_df.copy()

    commits_df["event"] = [[] for _ in range(len(commits_df))]
    commits_df["llm_output"] = ""
    commits_df["llm_timestamp"] = ""
    commits_df["source"] = "commit"

    msg_col = "commit_message" if "commit_message" in commits_df.columns else None
    if msg_col is None:
        print("[WARN] Commits CSV missing commit_message column. All commits will be commit_uninformative.")
        return _apply_default_uninformative(commits_df)

    for i, msg in enumerate(tqdm(commits_df[msg_col].fillna(""), desc="Commit message labelling")):
        msg_str = str(msg).strip()

        if msg_str in cache:
            label = cache[msg_str]
            llm_raw = "cached"
        else:
            label, llm_raw = classify_commit_message(msg_str)
            cache[msg_str] = label

        commits_df.at[i, "event"] = append_event(commits_df.at[i, "event"], label)
        commits_df.at[i, "llm_output"] = llm_raw if llm_raw else ""
        commits_df.at[i, "llm_timestamp"] = RUN_TIMESTAMP if llm_raw else ""

    return commits_df


def _set_commit_timestamps(
    commits_df: pd.DataFrame,
    pr_time_lookup: dict,
) -> pd.DataFrame:
    """Best-effort created_at for commits: commit timestamp column if present, else PR created_at."""
    commits_df = commits_df.copy()

    commit_time_col = _pick_commit_time_column(commits_df)
    if commit_time_col:
        commits_df["created_at"] = pd.to_datetime(commits_df[commit_time_col], errors="coerce")
    else:
        commits_df["created_at"] = pd.NaT

    commits_df["created_at"] = commits_df["created_at"].combine_first(
        commits_df["pr_id"].map(pr_time_lookup)
    )
    return commits_df


def _set_commit_author(commits_df: pd.DataFrame) -> pd.DataFrame:
    """Best-effort pr_author for commits."""
    commits_df = commits_df.copy()

    if "author" in commits_df.columns:
        commits_df["pr_author"] = commits_df["author"]
    elif "commit_author" in commits_df.columns:
        commits_df["pr_author"] = commits_df["commit_author"]
    else:
        commits_df["pr_author"] = "unknown"

    commits_df["pr_author"] = commits_df["pr_author"].replace("", np.nan).fillna("unknown")
    return commits_df


def _label_pr_docs_and_merge(prs_df: pd.DataFrame) -> pd.DataFrame:
    """Add feature_documented/undocumented + merge labels to prs_df."""
    prs_df = prs_df.copy()

    prs_df["event"] = [[] for _ in range(len(prs_df))]
    prs_df["llm_output"] = ""
    prs_df["llm_timestamp"] = ""
    prs_df["source"] = "pr"

    # docs_updated -> feature_documented / feature_undocumented
    for i, row in prs_df.iterrows():
        docs_flag = bool(row.get("docs_updated", False))
        doc_label = "feature_documented" if docs_flag else "feature_undocumented"
        prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], doc_label)

    # merge labels via utility
    merge_labels_df = label_merge_state(prs_df)
    merge_event_map = merge_labels_df.set_index("pr_id")["event"].to_dict()

    for i, row in prs_df.iterrows():
        pr_id = row.get("pr_id")
        merge_event = merge_event_map.get(pr_id)
        if merge_event:
            prs_df.at[i, "event"] = append_event(prs_df.at[i, "event"], merge_event)

    # author normalization
    if "pr_author" not in prs_df.columns:
        prs_df["pr_author"] = "unknown"
    prs_df["pr_author"] = prs_df["pr_author"].replace("", np.nan).fillna("unknown")

    return prs_df


def _filter_and_format_comm_output(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only comm labels and ensure event is stored as stringified list."""
    df = df.copy()
    df["event_list"] = df["event"].apply(_keep_comm_events)
    df = df[df["event_list"].map(len) > 0].copy()
    df["event"] = df["event_list"].apply(lambda x: str(x))
    return df


def _build_pr_time_lookup(prs_df: pd.DataFrame) -> dict:
    """Create pr_id -> created_at lookup and write it to PR_LOOKUP_PATH."""
    pr_lookup = (
        prs_df[["pr_id", "created_at"]]
        .dropna(subset=["pr_id", "created_at"])
        .drop_duplicates(subset=["pr_id"])
    )
    pr_time_lookup = pr_lookup.set_index("pr_id")["created_at"].to_dict()
    pr_lookup.to_csv(PR_LOOKUP_PATH, index=False)
    return pr_time_lookup


def _normalize_pr_ids_in_place(prs_df: pd.DataFrame, commits_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    named_dfs = [("prs_df", prs_df), ("commits_df", commits_df)]
    normalize_pr_ids(named_dfs)
    prs_df, commits_df = [df for _, df in named_dfs]
    return prs_df, commits_df


def _process_team_folder(
    team_folder: str,
    team_name: str,
    cache: dict[str, str],
) -> None:
    prs_patterns = [p.format(team=team_name) for p in PRS_PATTERN_TEMPLATES]
    commits_patterns = [p.format(team=team_name) for p in COMMITS_PATTERN_TEMPLATES]

    prs_path = find_file(team_folder, prs_patterns)
    commits_path = find_file(team_folder, commits_patterns)

    missing = []
    if not prs_path:
        missing.append("PRs file")
    if not commits_path:
        missing.append("Commits file")

    if missing:
        print(f"❌ Missing files for {team_name}: {', '.join(missing)}")
        print("Skipping this team.\n")
        return

    print(f"[OK] Found required CSVs for {team_name}")
    print(f"  - PRs:     {os.path.basename(prs_path)}")
    print(f"  - Commits: {os.path.basename(commits_path)}")

    # Preprocess (CLEAN files)
    clean_prs_path, clean_commits_path = preprocess_team_csvs(
        team_name=team_name,
        team_folder=team_folder,
        prs_path=prs_path,
        commits_path=commits_path,
    )

    # Load CLEAN CSVs
    print("[INFO] Loading CLEAN CSVs with parsed timestamps...")
    prs_df = pd.read_csv(clean_prs_path, parse_dates=["created_at"])
    commits_df = pd.read_csv(clean_commits_path)

    # Normalize PR IDs
    prs_df, commits_df = _normalize_pr_ids_in_place(prs_df, commits_df)

    # Timestamp lookup
    print("[STEP 0] Building PR created_at lookup...")
    pr_time_lookup = _build_pr_time_lookup(prs_df)

    # Commit informativeness
    print("[STEP 1] Labelling commit informativeness (cached)...")
    commits_df = _label_commit_informativeness(commits_df, cache)
    commits_df = _set_commit_timestamps(commits_df, pr_time_lookup)
    commits_df = _set_commit_author(commits_df)

    # PR docs + merge labels
    print("[STEP 2] Labelling PR documentation + merge state...")
    prs_df = _label_pr_docs_and_merge(prs_df)

    # Filter to COMM_LABELS and write output
    print("[STEP 3] Building final Communication-labelled output...")
    commits_out = _filter_and_format_comm_output(commits_df)
    prs_out = _filter_and_format_comm_output(prs_df)

    combined = pd.concat([commits_out, prs_out], ignore_index=True)
    combined["created_at"] = pd.to_datetime(combined["created_at"], errors="coerce")
    combined = combined.sort_values("created_at").reset_index(drop=True)

    comm_output_path = os.path.join(DATA_FOLDER, f"communication_labels_{team_name}.csv")
    combined.to_csv(comm_output_path, index=False)
    print(f"[OK] Communication labels saved → {comm_output_path} ({len(combined)} rows)")

    # Optional CLEAN_*
    try:
        clean_path = create_clean_comm_label_csv(comm_output_path)
        print(f"[OK] CLEAN communication labels saved → {clean_path}")
    except Exception as e:
        print(f"[WARN] Could not create CLEAN comm labels for {team_name}: {e}")


def process_all_teams() -> None:
    team_folders = sorted(
        p for p in glob.glob(os.path.join(DATA_FOLDER, "*"))
        if os.path.isdir(p) and not os.path.basename(p).startswith(".")
    )
    if not team_folders:
        raise FileNotFoundError(f"❌ No team folders found in {DATA_FOLDER}")

    print(f"[INFO] Found {len(team_folders)} team folders:")
    for t in team_folders:
        print(" -", os.path.basename(t))

    cache = _load_commit_cache()

    for team_folder in team_folders:
        team_name = os.path.basename(team_folder)
        print(f"\n{'='*70}")
        print(f"Processing {team_name} (Communication labels) ...")
        print('='*70)

        _process_team_folder(
            team_folder=team_folder,
            team_name=team_name,
            cache=cache,
        )

    _save_commit_cache(cache)


if __name__ == "__main__":
    process_all_teams()