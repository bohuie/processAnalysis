from __future__ import annotations

from typing import Iterable, Tuple
import pandas as pd


def normalize_pr_ids(
    named_dfs: Iterable[Tuple[str, pd.DataFrame]],
    pattern: str = r"(\d+)",
) -> None:
    """
    Normalize `pr_id` columns across multiple DataFrames in-place.

    For each (name, df) pair:
      - If df has a 'pr_id' column:
          * Cast to string
          * Extract the first group of digits via regex (default: r"(\\d+)")
          * Cast to pandas Int64 (nullable integer)
      - Print a debug line with the number of unique pr_ids.

    Parameters
    ----------
    named_dfs : iterable of (str, pd.DataFrame)
        Pairs of (df_name, dataframe) to process.
    pattern : str, optional
        Regex pattern with one capturing group to extract the numeric part
        (default: r"(\\d+)").
    """
    for df_name, df in named_dfs:
        if "pr_id" not in df.columns:
            continue

        df["pr_id"] = (
            df["pr_id"]
            .astype(str)
            .str.extract(pattern)[0]
            .astype("Int64")
        )

        print(f"[DEBUG] Normalized pr_id in {df_name}: {df['pr_id'].nunique()} unique IDs")
