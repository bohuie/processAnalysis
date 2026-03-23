"""
Clean and impute labels for Branching and PR data.
"""
from __future__ import annotations
import os
import ast
import pandas as pd
import numpy as np

# PR-level label types to keep (filter out per-file labels)
PR_LEVEL_LABELS = {
    "Branch Name",
    "Features Per Branch",
    "Repository Status",
    "Feature Size",
    "Refactor Size",
    "PR Status",
    "Merge State"
}

MERGE_EVENTS = {"reviewed_merge", "self_merge"}
NO_MERGE_EVENTS = {"no_merge"}


def _parse_event_cell(ev) -> str:
    """
    Parse the event cell which might be a string or list.
    Returns the event as a clean string.
    """
    if ev is None or (isinstance(ev, float) and pd.isna(ev)):
        return ""

    if isinstance(ev, str):
        s = ev.strip()
        # If it looks like a list literal, parse it
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list) and len(parsed) > 0:
                    return str(parsed[0])
            except Exception:
                pass
        return s

    if isinstance(ev, list) and len(ev) > 0:
        return str(ev[0])

    return str(ev)


def _parse_event_cell_list(ev) -> list[str]:
    """
    The original CSV for PR labels stores events like "['reviewed_merge']" (string).
    This returns a real list[str]. If it's already a string label, returns [label].
    """
    if ev is None or (isinstance(ev, float) and pd.isna(ev)):
        return []

    if isinstance(ev, list):
        return [e for e in ev if isinstance(e, str)]

    if isinstance(ev, str):
        s = ev.strip()
        # If it looks like a list literal, parse it
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [e for e in parsed if isinstance(e, str)]
            except Exception:
                pass
        # Otherwise treat it as a single label
        return [s]

    return []


def _pick_timestamp(row: pd.Series) -> str | None:
    """
    Timestamp selection logic for Branching labels:
    - For Merge State: use merged_at
    - For everything else: use created_at
    """
    main_label = row.get("main_label", "")
    
    # For Merge State, prefer merged_at
    if main_label == "Merge State":
        val = row.get("merged_at", None)
        if val is not None and not (isinstance(val, float) and pd.isna(val)) and str(val).strip():
            dt = pd.to_datetime(val, errors="coerce", utc=True)
            if not pd.isna(dt):
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Default to created_at
    val = row.get("created_at", None)
    if val is None or (isinstance(val, float) and pd.isna(val)) or not str(val).strip():
        return None
    
    dt = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(dt):
        return str(val)
    
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pick_timestamp_pr(row: pd.Series, events: list[str]) -> str | None:
    """
    Timestamp rules for PR labels:
    - default: created_at
    - if reviewed_merge/self_merge: merged_at
    - if no_merge: updated_at
    If the chosen column is missing/NaN, fall back to created_at.
    """
    # Decide which column to use (precedence: merge > no_merge > created_at)
    use_col = "created_at"
    if any(e in MERGE_EVENTS for e in events):
        use_col = "merged_at"
    elif any(e in NO_MERGE_EVENTS for e in events):
        use_col = "updated_at"

    # Pull value and fall back if needed
    val = row.get(use_col, None)
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        val = row.get("created_at", None)

    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        return None

    # Normalize to ISO-ish string
    dt = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(dt):
        # if parsing fails, keep raw
        return str(val)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_and_impute_branch_names(input_path: str, output_path: str):
    """
    Reads a CSV, imputes missing branch names by propagating the valid branch name for each PR ID,
    and saves the cleaned CSV.

    Logic:
    1. Read CSV.
    2. Convert empty strings to NaN.
    3. Ensure pr_id is treated as numeric (if possible) or consistent type.
    4. Group by pr_id and fill NaN branch_name with first valid value found for that pr_id.
    5. Save to output_path.
    """
    if not os.path.exists(input_path):
        return  # Gracefully handle non-existent file

    try:
        df = pd.read_csv(input_path)
    except pd.errors.EmptyDataError:
        return # Gracefully handle empty file

    if df.empty:
        return

    if 'pr_id' not in df.columns or 'branch_name' not in df.columns:
        return

    # Convert empty strings to NaN
    df['branch_name'] = df['branch_name'].replace(r'^\s*$', np.nan, regex=True)

    # Convert float PR IDs to Int64 (nullable int) to handle NaNs if any, or just consistent type
    if pd.api.types.is_float_dtype(df['pr_id']):
        # If all are integers, convert safely
        try:
            # Int64 handles NaN
            df['pr_id'] = df['pr_id'].astype('Int64')
        except Exception:
            pass

    # Impute branch_name per pr_id
    # We use transform('first') to propagate the first valid branch name to all rows in the group
    # This ensures consistency for the whole PR and satisfies the "use first one" requirement
    df['branch_name'] = df.groupby('pr_id', group_keys=False)['branch_name'].transform('first')
    
    # If there are still NaNs (e.g. some groups had NO valid branch name), they remain NaN.

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    df.to_csv(output_path, index=False)


def create_clean_branching_label_csv(
    input_csv_path: str, 
    output_csv_path: str | None = None,
    include_main_label: bool = False
) -> str:
    """
    Reads {team}_labels_branching_and_structure.csv and creates a clean version
    with only PR-level events (no per-file Feature/Refactor Size details).
    """
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    df = pd.read_csv(input_csv_path)
    
    # Validate required columns
    required = {"pr_id", "event", "main_label", "created_at"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns in {input_csv_path}: {sorted(missing)}")

    # Default output path
    if output_csv_path is None:
        folder = os.path.dirname(input_csv_path)
        clean_folder = os.path.join(folder, "clean")
        os.makedirs(clean_folder, exist_ok=True)
        base = os.path.basename(input_csv_path)
        output_csv_path = os.path.join(clean_folder, f"CLEAN_{base}")

    print(f"[INFO] Input: {input_csv_path}")
    print(f"[INFO] Total rows: {len(df)}")
    
    # Filter to keep only PR-level labels
    pr_level_df = df[df["main_label"].isin(PR_LEVEL_LABELS)].copy()
    print(f"[INFO] PR-level rows after filtering: {len(pr_level_df)}")
    
    # Build output rows
    out_rows = []
    for _, row in pr_level_df.iterrows():
        event = _parse_event_cell(row.get("event"))
        ts = _pick_timestamp(row)
        
        out_row = {
            "pr_id": row.get("pr_id"),
            "timestamp": ts,
            "event": event,
        }
        
        if include_main_label:
            out_row["main_label"] = row.get("main_label")
        
        out_rows.append(out_row)
    
    cols = ["pr_id", "timestamp", "event"]
    if include_main_label:
        cols.append("main_label")

    out_df = pd.DataFrame(out_rows, columns=cols)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    out_df.to_csv(output_csv_path, index=False)
    
    print(f"[SUCCESS] Clean labels saved to: {output_csv_path}")
    return output_csv_path


def create_clean_pr_label_csv(input_csv_path: str, output_csv_path: str | None = None) -> str:
    """
    Reads pr_labels_{team}.csv and writes CLEAN_pr_labels_{team}.csv containing:
      pr_id, timestamp, event
    """
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    df = pd.read_csv(input_csv_path)

    required = {"pr_id", "event", "created_at", "updated_at", "merged_at"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns in {input_csv_path}: {sorted(missing)}")

    # Default output path
    if output_csv_path is None:
        folder = os.path.dirname(input_csv_path)
        base = os.path.basename(input_csv_path)
        output_csv_path = os.path.join(folder, f"CLEAN_{base}")

    # Build output rows
    out_rows = []
    for _, row in df.iterrows():
        events = _parse_event_cell_list(row.get("event"))
        ts = _pick_timestamp_pr(row, events)

        out_rows.append(
            {
                "pr_id": row.get("pr_id"),
                "timestamp": ts,
                # keep EXACT same event cell as in original CSV (string form)
                "event": row.get("event"),
            }
        )

    out_df = pd.DataFrame(out_rows, columns=["pr_id", "timestamp", "event"])
    out_df.to_csv(output_csv_path, index=False)
    return output_csv_path
