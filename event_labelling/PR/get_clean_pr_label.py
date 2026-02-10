from __future__ import annotations
import os
import ast
import pandas as pd
from typing import Optional


MERGE_EVENTS = {"reviewed_merge", "self_merge"}
NO_MERGE_EVENTS = {"no_merge"}


def _parse_event_cell(ev) -> list[str]:
    """
    The original CSV stores events like "['reviewed_merge']" (string).
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


def _pick_timestamp_row(row: pd.Series, events: list[str]) -> Optional[str]:
    """
    Timestamp rules:
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

    # Normalize to ISO-ish string (optional but helpful)
    dt = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(dt):
        # if parsing fails, keep raw
        return str(val)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_clean_pr_label_csv(input_csv_path: str, output_csv_path: Optional[str] = None) -> str:
    """
    Reads pr_labels_{team}.csv and writes CLEAN_pr_labels_{team}.csv containing:
      pr_id, timestamp, event

    Returns output path.
    """
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    df = pd.read_csv(input_csv_path)

    required = {"pr_id", "event", "created_at", "updated_at", "merged_at"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns in {input_csv_path}: {sorted(missing)}")

    # Default output path: prefix CLEAN_
    if output_csv_path is None:
        folder = os.path.dirname(input_csv_path)
        base = os.path.basename(input_csv_path)
        output_csv_path = os.path.join(folder, f"CLEAN_{base}")

    # Build output rows
    out_rows = []
    for _, row in df.iterrows():
        events = _parse_event_cell(row.get("event"))
        ts = _pick_timestamp_row(row, events)

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
