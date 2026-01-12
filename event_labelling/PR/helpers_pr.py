import os
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
