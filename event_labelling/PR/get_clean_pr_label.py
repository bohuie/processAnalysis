from __future__ import annotations
import os
import sys

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import from the new utility
from process_model.clean import create_clean_pr_label_csv

# Re-export key function for backward compatibility with existing imports


__all__ = ["create_clean_pr_label_csv"]
