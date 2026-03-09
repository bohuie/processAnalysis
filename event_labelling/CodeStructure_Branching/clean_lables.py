"""
Create clean branching label CSV with only PR-level events (no per-file details).

This script filters out per-file Feature Size and Refactor Size labels,
keeping only the high-level PR labels: Branch Name, Features Per Branch,
Repository Status, PR Status, and Merge State.

Output: CLEAN_{team}_labels_branching_and_structure.csv with columns:
  - pr_id
  - timestamp
  - event
  - main_label (optional, for reference)
"""
from __future__ import annotations
import os
import ast
import pandas as pd
from typing import Optional


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


def _pick_timestamp(row: pd.Series) -> Optional[str]:
    """
    Timestamp selection logic:
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


def create_clean_branching_label_csv(
    input_csv_path: str, 
    output_csv_path: Optional[str] = None,
    include_main_label: bool = False
) -> str:
    """
    Reads {team}_labels_branching_and_structure.csv and creates a clean version
    with only PR-level events (no per-file Feature/Refactor Size details).
    
    Args:
        input_csv_path: Path to the full branching labels CSV
        output_csv_path: Optional output path. If None, uses clean/ subfolder with CLEAN_ prefix
        include_main_label: If True, includes main_label column in output
    
    Returns:
        Path to the created clean CSV file
    """
    if not os.path.exists(input_csv_path):
        raise FileNotFoundError(f"Input file not found: {input_csv_path}")

    df = pd.read_csv(input_csv_path)
    
    # Validate required columns
    required = {"pr_id", "event", "main_label", "created_at"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns in {input_csv_path}: {sorted(missing)}")

    # Default output path: clean/ subfolder with CLEAN_ prefix
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
    
    # Show breakdown by label type
    print("[INFO] Breakdown by label type:")
    for label_type in PR_LEVEL_LABELS:
        count = (pr_level_df["main_label"] == label_type).sum()
        if count > 0:
            print(f"  - {label_type}: {count}")
    
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
    
    # Create output DataFrame
    if include_main_label:
        out_df = pd.DataFrame(out_rows, columns=["pr_id", "timestamp", "event", "main_label"])
    else:
        out_df = pd.DataFrame(out_rows, columns=["pr_id", "timestamp", "event"])
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    
    # Save to CSV
    out_df.to_csv(output_csv_path, index=False)
    
    print(f"[SUCCESS] Clean labels saved to: {output_csv_path}")
    print(f"[INFO] Output rows: {len(out_df)}")
    
    return output_csv_path


def process_all_teams(base_folder: str = "data/graph_labels", include_main_label: bool = False):
    """
    Process all team branching label files in the given folder.
    
    Args:
        base_folder: Folder containing *_labels_branching_and_structure.csv files
        include_main_label: If True, includes main_label column in output
    """
    import glob
    
    if not os.path.exists(base_folder):
        print(f"[ERROR] Folder not found: {base_folder}")
        return
    
    pattern = os.path.join(base_folder, "*_labels_branching_and_structure.csv")
    files = glob.glob(pattern)
    
    # Exclude already cleaned files
    files = [f for f in files if not os.path.basename(f).startswith("CLEAN_")]
    
    if not files:
        print(f"[WARN] No matching files found in {base_folder}")
        return
    
    print(f"[INFO] Found {len(files)} file(s) to process")
    print("=" * 70)
    
    for file_path in files:
        team_name = os.path.basename(file_path).replace("_labels_branching_and_structure.csv", "")
        print(f"\n[INFO] Processing: {team_name}")
        print("-" * 70)
        
        try:
            create_clean_branching_label_csv(file_path, include_main_label=include_main_label)
        except Exception as e:
            print(f"[ERROR] Failed to process {team_name}: {e}")
        
    print("\n" + "=" * 70)
    print("[COMPLETE] All files processed")


if __name__ == "__main__":
    import sys
    import glob
    
    # Usage examples:
    # python get_clean_branching_label.py                                    # Process all *_labels_branching_and_structure.csv in current directory
    # python get_clean_branching_label.py /path/to/file.csv                  # Process single file
    # python get_clean_branching_label.py /path/to/folder --include-label    # Process folder with main_label column
    
    include_main_label = "--include-label" in sys.argv
    
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        path = sys.argv[1]
        
        if os.path.isfile(path):
            # Process single file
            input_dir = os.path.dirname(path) or "."
            clean_dir = os.path.join(input_dir, "clean")
            os.makedirs(clean_dir, exist_ok=True)
            output_name = "CLEAN_" + os.path.basename(path)
            output_path = os.path.join(clean_dir, output_name)
            create_clean_branching_label_csv(path, output_path, include_main_label=include_main_label)
        elif os.path.isdir(path):
            # Process all files in folder
            process_all_teams(path, include_main_label=include_main_label)
        else:
            print(f"[ERROR] Path not found: {path}")
    else:
        # Default: look for files in common locations
        search_paths = [
            "../../data/graph_labels",
            "data/graph_labels",
            ".",
            "data/csv"
        ]
        
        found_files = []
        for search_path in search_paths:
            if os.path.exists(search_path):
                pattern = os.path.join(search_path, "*_labels_branching_and_structure.csv")
                files = glob.glob(pattern)
                # Exclude already cleaned files
                files = [f for f in files if not os.path.basename(f).startswith("CLEAN_")]
                found_files.extend(files)
        
        if not found_files:
            print("[ERROR] No *_labels_branching_and_structure.csv files found")
            print("Search locations:")
            for path in search_paths:
                print(f"  - {path}")
            print("\nUsage: python get_clean_branching_label.py [file_or_folder]")
        else:
            print(f"[INFO] Found {len(found_files)} file(s) to process")
            print("=" * 70)
            
            for file_path in found_files:
                team_name = os.path.basename(file_path).replace("_labels_branching_and_structure.csv", "")
                print(f"\n[INFO] Processing: {team_name}")
                print("-" * 70)
                
                try:
                    input_dir = os.path.dirname(file_path)
                    clean_dir = os.path.join(input_dir, "clean")
                    os.makedirs(clean_dir, exist_ok=True)
                    output_name = "CLEAN_" + os.path.basename(file_path)
                    output_path = os.path.join(clean_dir, output_name)
                    create_clean_branching_label_csv(file_path, output_path, include_main_label=include_main_label)
                except Exception as e:
                    print(f"[ERROR] Failed to process {team_name}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print("\n" + "=" * 70)
            print("[COMPLETE] All files processed")