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
    

LOG_PATTERN = re.compile(r"\blog(s?)\b", re.IGNORECASE)


def drop_log_rows(df: pd.DataFrame, df_label: str) -> pd.DataFrame:
    """
    Remove rows where ANY cell contains the word 'log' or 'logs' (case-insensitive).
    Uses regex: \\blog(s?)\\b
    """
    if df.empty:
        print(f"[INFO] {df_label}: DataFrame empty, skipping log filter.")
        return df

    # Convert all cells to string for safe matching
    str_df = df.astype(str)

    # For each column, check if it contains 'log' / 'logs', then OR across columns
    col_matches = str_df.apply(
        lambda col: col.str.contains(LOG_PATTERN, na=False),
        axis=0
    )
    row_has_log = col_matches.any(axis=1)

    before = len(df)
    filtered_df = df[~row_has_log].copy()
    removed = before - len(filtered_df)

    print(f"[STEP -1B] {df_label}: removed {removed} rows containing 'log'/'logs' "
          f"({before} -> {len(filtered_df)}).")
    return filtered_df