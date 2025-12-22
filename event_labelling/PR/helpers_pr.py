import os
import re
import pandas as pd
from src.utils.botFilter import filter_bots_from_multiple_columns

# === HELPERS =========================================================
def append_event(event_list, new_event):
    """Safely append a new label to the event list (avoiding duplicates)."""
    if not isinstance(event_list, list):
        event_list = []
    if new_event and new_event not in event_list:
        event_list.append(new_event)
    return event_list


def find_file(folder, patterns):
    """Return the first existing path matching any pattern in a folder."""
    for pattern in patterns:
        potential_path = os.path.join(folder, pattern)
        if os.path.exists(potential_path):
            return potential_path
    return None

# Utility to drop bot rows from any *author*-like and merged_by columns
def drop_bots_in_author_like_columns(df: pd.DataFrame, df_label: str) -> pd.DataFrame:
    author_cols = [c for c in df.columns if "author" in c.lower()]
    bot_cols = list(author_cols)
    if "merged_by" in df.columns:
        bot_cols.append("merged_by")

    if not bot_cols:
        print(f"[INFO] No author/merged_by columns found in {df_label}, skipping bot filter.")
        return df

    print(f"[STEP -1] Filtering bots in {df_label} using columns: {bot_cols}")
    return filter_bots_from_multiple_columns(
        df,
        username_columns=bot_cols,
        filter_mode="any",   # drop row if ANY of these columns is a bot
        inplace=False,
        verbose=True,
    )
    

LOG_PATTERN = re.compile(
    r"(?i)(?:\blogs?\b|weeklylogs?\b|teamlogs?\b|personallogs?\b)"
)


def drop_log_rows(df: pd.DataFrame, df_label: str) -> pd.DataFrame:
    """
    If ANY row belonging to a pr_id contains a log pattern in ANY cell,
    drop ALL rows with that pr_id.

    (Fallback: if 'pr_id' is missing, behave like the old row-level filter.)
    """
    if df.empty:
        print(f"[INFO] {df_label}: DataFrame empty, skipping log filter.")
        return df

    # If we can't do PR-level removal, fall back to old behavior
    if "pr_id" not in df.columns:
        print(f"[WARN] {df_label}: no 'pr_id' column found — falling back to row-level log filtering.")
        str_df = df.astype(str)
        col_matches = str_df.apply(lambda col: col.str.contains(LOG_PATTERN, na=False), axis=0)
        row_has_log = col_matches.any(axis=1)
        before = len(df)
        filtered_df = df[~row_has_log].copy()
        removed = before - len(filtered_df)
        print(f"[STEP -1B] {df_label}: removed {removed} rows containing 'log'/'logs' "
              f"({before} -> {len(filtered_df)}).")
        return filtered_df

    # --- PR-level filtering ---
    # check all cells as strings, but EXCLUDE pr_id itself from matching
    cols_to_check = [c for c in df.columns if c != "pr_id"]
    if not cols_to_check:
        print(f"[INFO] {df_label}: only 'pr_id' column present — skipping log filter.")
        return df

    str_df = df[cols_to_check].astype(str)

    # row-level flags: does this row contain a log pattern anywhere?
    col_matches = str_df.apply(lambda col: col.str.contains(LOG_PATTERN, na=False), axis=0)
    row_has_log = col_matches.any(axis=1)

    # collect pr_ids to drop (any row in that pr_id matched)
    bad_pr_ids = (
        df.loc[row_has_log, "pr_id"]
          .dropna()
          .astype(str)  # robust in case some are Int64 / mixed
          .unique()
          .tolist()
    )

    before_rows = len(df)
    before_prs = df["pr_id"].nunique(dropna=True)

    if not bad_pr_ids:
        print(f"[STEP -1B] {df_label}: removed 0 log PRs ({before_rows} rows unchanged).")
        return df

    # drop ALL rows where pr_id is in bad_pr_ids
    filtered_df = df[~df["pr_id"].astype(str).isin(bad_pr_ids)].copy()

    after_rows = len(filtered_df)
    after_prs = filtered_df["pr_id"].nunique(dropna=True)

    print(
        f"[STEP -1B] {df_label}: removed {len(bad_pr_ids)} log PR_ids "
        f"({before_prs} -> {after_prs} PRs), "
        f"dropping {before_rows - after_rows} rows ({before_rows} -> {after_rows})."
    )

    return filtered_df
