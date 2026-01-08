import re
import pandas as pd

LOG_PATTERN = re.compile(r"(?i)(?:\blogs?\b|weeklylogs?\b|teamlogs?\b|personallogs?\b)")

def find_log_pr_ids(df: pd.DataFrame, df_label: str) -> set[str]:
    """
    Return the set of pr_id values (as strings) for which ANY row
    contains the log pattern in ANY non-pr_id column.
    """
    if df.empty:
        print(f"[INFO] {df_label}: empty df, no log PRs.")
        return set()

    if "pr_id" not in df.columns:
        print(f"[WARN] {df_label}: no pr_id column, cannot build global log-pr set from this df.")
        return set()

    cols_to_check = [c for c in df.columns if c != "pr_id"]
    if not cols_to_check:
        print(f"[INFO] {df_label}: only pr_id column present, no log PRs.")
        return set()

    str_df = df[cols_to_check].astype(str)
    col_matches = str_df.apply(lambda col: col.str.contains(LOG_PATTERN, na=False), axis=0)
    row_has_log = col_matches.any(axis=1)

    bad_pr_ids = (
        df.loc[row_has_log, "pr_id"]
          .dropna()
          .astype(str)
          .unique()
          .tolist()
    )

    out = set(bad_pr_ids)
    print(f"[STEP -1B DETECT] {df_label}: detected {len(out)} log PR_ids.")
    return out


def drop_pr_ids(df: pd.DataFrame, pr_ids_to_drop: set[str], df_label: str) -> pd.DataFrame:
    """
    Drop ALL rows whose pr_id is in pr_ids_to_drop.
    """
    if df.empty or not pr_ids_to_drop:
        print(f"[STEP -1B APPLY] {df_label}: nothing to drop.")
        return df

    if "pr_id" not in df.columns:
        print(f"[WARN] {df_label}: no pr_id column, cannot apply pr_id drop.")
        return df

    before_rows = len(df)
    before_prs = df["pr_id"].nunique(dropna=True)

    mask_keep = ~df["pr_id"].astype(str).isin(pr_ids_to_drop)
    filtered = df[mask_keep].copy()

    after_rows = len(filtered)
    after_prs = filtered["pr_id"].nunique(dropna=True)

    print(
        f"[STEP -1B APPLY] {df_label}: dropped {before_rows - after_rows} rows "
        f"({before_rows}->{after_rows}), PRs {before_prs}->{after_prs}."
    )
    return filtered