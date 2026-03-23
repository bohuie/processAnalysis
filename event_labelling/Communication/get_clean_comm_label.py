from __future__ import annotations
import os
import ast
import pandas as pd


MERGE_EVENTS = {"reviewed_merge", "self_merge"}
NO_MERGE_EVENTS = {"no_merge"}


def _parse_event_cell(ev) -> list[str]:
    """
    communication_labels CSV stores events like "['reviewed_merge']" (string).
    Return a real list[str].
    """
    if ev is None or (isinstance(ev, float) and pd.isna(ev)):
        return []

    if isinstance(ev, list):
        return [e for e in ev if isinstance(e, str)]

    if isinstance(ev, str):
        s = ev.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, list):
                    return [e for e in parsed if isinstance(e, str)]
            except Exception:
                pass
        return [s]

    return []


def _pick_timestamp(row: pd.Series, events: list[str]) -> str | None:
    """
    Timestamp rules (best-effort):
    - merge events -> merged_at (if present), else created_at
    - no_merge     -> updated_at (if present), else created_at
    - otherwise    -> created_at
    """
    use_col = "created_at"
    if any(e in MERGE_EVENTS for e in events):
        use_col = "merged_at"
    elif any(e in NO_MERGE_EVENTS for e in events):
        use_col = "updated_at"

    val = row.get(use_col, None)
    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        val = row.get("created_at", None)

    if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and not val.strip()):
        return None

    dt = pd.to_datetime(val, errors="coerce", utc=True)
    if pd.isna(dt):
        return str(val)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def create_clean_comm_label_csv(input_csv_path: str, output_csv_path: str | None = None) -> str:
    """
    Reads communication_labels_{team}.csv and writes CLEAN_communication_labels_{team}.csv containing:
      pr_id, timestamp, event
    """
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    df = pd.read_csv(input_csv_path)

    if "pr_id" not in df.columns or "event" not in df.columns:
        raise KeyError("communication labels CSV must include at least: pr_id, event")

    if output_csv_path is None:
        folder = os.path.dirname(input_csv_path)
        base = os.path.basename(input_csv_path)
        output_csv_path = os.path.join(folder, f"CLEAN_{base}")

    out_rows = []
    for _, row in df.iterrows():
        events = _parse_event_cell(row.get("event"))
        ts = _pick_timestamp(row, events)
        out_rows.append(
            {
                "pr_id": row.get("pr_id"),
                "timestamp": ts,
                "event": row.get("event"),
            }
        )

    out_df = pd.DataFrame(out_rows, columns=["pr_id", "timestamp", "event"])
    out_df.to_csv(output_csv_path, index=False)
    return output_csv_path