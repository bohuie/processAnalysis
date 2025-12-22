from __future__ import annotations

from typing import Iterable, Tuple, Any, Dict
import json
import re

import pandas as pd

from src.utils.anonymize_data import (
    anonymize_username,
    get_anonymized_usernames_file,
)


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

def _anonymize_cell(value: Any) -> Any:
    """Apply anonymize_username to a single cell if it looks like a real username."""
    if pd.isna(value):
        return value

    s = str(value).strip()
    if not s:
        return value

    # Delegate actual mapping + JSON handling to anonymize_username
    return anonymize_username(s)


def _load_anonymized_usernames() -> Dict[str, str]:
    """
    Load the real->fake username mapping from anonymized_usernames.json.

    Returns an empty dict if the file does not exist or is invalid.
    """
    path = get_anonymized_usernames_file()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        # No mapping yet; anonymize_author_columns will create entries
        return {}
    except Exception as e:
        print(f"[WARN] Failed to load anonymized usernames from {path}: {e}")
        return {}
    return {}


def _anonymize_series_with_mapping(
    series: pd.Series,
    mapping: Dict[str, str],
) -> pd.Series:
    """
    Replace any occurrence of real usernames in `mapping` with their fake names
    in the given Series (case-insensitive, substring-based).
    """
    if not mapping:
        return series

    s = series.astype(str)

    for real_name, fake in mapping.items():
        if not real_name:
            continue
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, fake, regex=True)

    return s


# ---------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------

def anonymize_author_columns(
    named_dfs: Iterable[Tuple[str, pd.DataFrame]],
) -> None:
    """
    Anonymize any column whose header contains 'author' (case-insensitive)
    or is exactly 'merged_by' (case-insensitive) across multiple DataFrames,
    in-place.

    For each (name, df) in named_dfs:
      - Find columns where 'author' is in the column name (lowercased),
        plus any column named 'merged_by' (lowercased).
      - Replace each non-empty cell in those columns with anonymize_username(value),
        which also updates anonymized_usernames.json.
    """
    for df_name, df in named_dfs:
        # Find author-related columns
        author_cols = [col for col in df.columns if "author" in col.lower()]
        merged_by_cols = [col for col in df.columns if col.lower() == "merged_by"]

        target_cols = list({*author_cols, *merged_by_cols})
        if not target_cols:
            continue

        print(f"[INFO] Anonymizing author/merged_by columns in {df_name}: {target_cols}")

        for col in target_cols:
            df[col] = df[col].apply(_anonymize_cell)


def anonymize_column(
    series: pd.Series,
    mapping: Dict[str, str] | None = None,
) -> pd.Series:
    """
    Anonymize occurrences of real usernames inside a generic text column.

    - If `mapping` is None, it is loaded from anonymized_usernames.json.
    - Replaces any substring matching a real username (case-insensitive)
      with its fake counterpart.

    Typical use:
        df["pr_description"] = anonymize_column(df["pr_description"])
    """
    if mapping is None:
        mapping = _load_anonymized_usernames()

    return _anonymize_series_with_mapping(series, mapping)


def anonymize_branch_names(
    series: pd.Series,
    mapping: Dict[str, str] | None = None,
) -> pd.Series:
    """
    Anonymize branch names by replacing username parts within the full branch string.

    - If `mapping` is None, it is loaded from anonymized_usernames.json.
    - Uses the same substring replacement logic as anonymize_column.

    Typical use:
        prs_df["head_branch"] = anonymize_branch_names(prs_df["head_branch"])
    """
    if mapping is None:
        mapping = _load_anonymized_usernames()

    return _anonymize_series_with_mapping(series, mapping)

