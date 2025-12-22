# check_last_state_per_pr.py
import os, re, glob, ast
import pandas as pd
import numpy as np

# ---------- Paths ----------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
DATA_FOLDER = os.path.join(ROOT, "data", "csv")

OUT_DIR = os.path.join(ROOT, "data", "outputs", "pr", "debug_checks")
os.makedirs(OUT_DIR, exist_ok=True)

CLEAN_PREFIX = "CLEAN_pr_labels_"
TEAM_RE = re.compile(r"^CLEAN_pr_labels_(year-long-project-team-\d+)\.csv$", re.IGNORECASE)

# IMPORTANT: use the merge event names that exist in YOUR CLEAN files
# (Your old graphing.py uses these; your earlier transition script used self_merged by mistake)
MERGE_STATES = {"self_merge", "no_merge", "reviewed_merge"}

def discover_clean_team_files() -> list[str]:
    hits = glob.glob(os.path.join(DATA_FOLDER, f"{CLEAN_PREFIX}year-long-project-team-*.csv"))
    files = sorted(set(hits))
    if not files:
        raise FileNotFoundError(
            f"No CLEAN PR label CSVs found. Expected e.g.\n"
            f"  {os.path.join(DATA_FOLDER, 'CLEAN_pr_labels_year-long-project-team-7.csv')}"
        )
    return files

def parse_team_name_and_number(fp: str) -> tuple[str, str]:
    base = os.path.basename(fp)
    m = TEAM_RE.match(base)
    team_name = m.group(1) if m else "unknown-team"
    num_m = re.search(r"team-(\d+)", team_name)
    team_number = num_m.group(1) if num_m else "unknown"
    return team_name, team_number

def normalize_event_field(event) -> list[str]:
    """Parse list-like strings into list; otherwise wrap scalar as single-item list."""
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

def load_and_flatten(fp: str) -> pd.DataFrame:
    df = pd.read_csv(fp, low_memory=False)

    required = {"pr_id", "timestamp", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{fp} missing columns: {missing}")

    df["pr_id"] = pd.to_numeric(df["pr_id"], errors="coerce").astype("Int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

    # stable ordering within identical timestamps
    df["_row_idx"] = np.arange(len(df))

    df["event_list"] = df["event"].apply(normalize_event_field)
    df = df.explode("event_list", ignore_index=True)
    df["event"] = df["event_list"].astype(str).str.strip()

    df = df.dropna(subset=["pr_id", "timestamp"])
    df = df[df["event"].ne("")]

    df = df.sort_values(["pr_id", "timestamp", "_row_idx"]).reset_index(drop=True)

    return df[["pr_id", "timestamp", "event"]]

def main():
    files = discover_clean_team_files()
    print(f"[INFO] Found {len(files)} CLEAN files.")

    all_last = []
    all_bad = []

    for fp in files:
        team_name, team_number = parse_team_name_and_number(fp)
        flat = load_and_flatten(fp)

        # last chronological event per pr_id
        last_rows = (
            flat.groupby("pr_id", as_index=False)
                .tail(1)
                .copy()
        )
        last_rows.insert(0, "team_number", team_number)
        last_rows.insert(0, "team_name", team_name)
        last_rows.rename(columns={"event": "last_event", "timestamp": "last_timestamp"}, inplace=True)

        # classify
        last_rows["is_merge_state"] = last_rows["last_event"].isin(MERGE_STATES)

        bad = last_rows[~last_rows["is_merge_state"]].copy()

        print(f"[TEAM {team_number}] PR sessions: {len(last_rows)} | bad last events: {len(bad)}")

        all_last.append(last_rows)
        if not bad.empty:
            all_bad.append(bad)

            # optional: write per-team bads
            bad_fp = os.path.join(OUT_DIR, f"bad_last_events_team_{team_number}.csv")
            bad.to_csv(bad_fp, index=False)

    # write combined outputs
    last_all = pd.concat(all_last, ignore_index=True) if all_last else pd.DataFrame()
    last_all_fp = os.path.join(OUT_DIR, "last_event_per_pr_all_teams.csv")
    last_all.to_csv(last_all_fp, index=False)

    if all_bad:
        bad_all = pd.concat(all_bad, ignore_index=True)
    else:
        bad_all = pd.DataFrame(columns=["team_name","team_number","pr_id","last_timestamp","last_event","is_merge_state"])

    bad_all_fp = os.path.join(OUT_DIR, "bad_last_events_all_teams.csv")
    bad_all.to_csv(bad_all_fp, index=False)

    # quick summary: top bad last_event types
    if not bad_all.empty:
        print("\n[SUMMARY] Most common bad last_event values:")
        print(bad_all["last_event"].value_counts().head(20).to_string())

    print("\n[OK] Wrote outputs to:", OUT_DIR)
    print(" - last_event_per_pr_all_teams.csv")
    print(" - bad_last_events_all_teams.csv")
    print(" - bad_last_events_team_<N>.csv (when applicable)")

if __name__ == "__main__":
    main()
