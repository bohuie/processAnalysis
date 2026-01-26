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
import sys

# Ensure project root is in path to allow imports from src/process_model
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import from the new utility
from process_model.clean import create_clean_branching_label_csv


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
        print(f"\\n[INFO] Processing: {team_name}")
        print("-" * 70)
        
        try:
            create_clean_branching_label_csv(file_path, include_main_label=include_main_label)
        except Exception as e:
            print(f"[ERROR] Failed to process {team_name}: {e}")
        
    print("\\n" + "=" * 70)
    print("[COMPLETE] All files processed")


if __name__ == "__main__":
    import glob
    
    # Usage examples:
    # python clean_lable.py                                    # Process all *_labels_branching_and_structure.csv in current directory
    # python clean_lable.py /path/to/file.csv                  # Process single file
    # python clean_lable.py /path/to/folder --include-label    # Process folder with main_label column
    
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
            print("\\nUsage: python clean_lable.py [file_or_folder]")
        else:
            print(f"[INFO] Found {len(found_files)} file(s) to process")
            print("=" * 70)
            
            for file_path in found_files:
                team_name = os.path.basename(file_path).replace("_labels_branching_and_structure.csv", "")
                print(f"\\n[INFO] Processing: {team_name}")
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
            
            print("\\n" + "=" * 70)
            print("[COMPLETE] All files processed")
