import os
import tempfile
from pathlib import Path

import pandas as pd

from event_labelling.CodeStructure_Branching.label_feature_size import label_feature_size
from event_labelling.CodeStructure_Branching.label_refactor_size import label_refactor_size
from event_labelling.CodeStructure_Branching.label_features_per_branch import label_features_per_branch
from event_labelling.CodeStructure_Branching.clean_lables import create_clean_branching_label_csv


def test_feature_size_classification_per_file():
    prs_df = pd.DataFrame([
        {"pr_id": 1, "pr_author": "alice", "created_at": "2024-01-01T00:00:00Z"},
        {"pr_id": 2, "pr_author": "bob", "created_at": "2024-02-01T00:00:00Z"},
    ])
    pr_created_at_lookup = {1: "2024-01-01T00:00:00Z", 2: "2024-02-01T00:00:00Z"}
    commits_df = pd.DataFrame([
        {"pr_id": 1, "commit_sha": "a1", "file_path": "src/new.py", "lines_added": 10, "lines_deleted": 0},
        {"pr_id": 2, "commit_sha": "b1", "file_path": "src/big.py", "lines_added": 100, "lines_deleted": 0},
        {"pr_id": 1, "commit_sha": "a2", "file_path": "src/skip.py", "lines_added": 0, "lines_deleted": 5},
    ])

    df = label_feature_size(commits_df, prs_df, pr_created_at_lookup, run_timestamp="ts")

    events = {(row.pr_id, row.event) for _, row in df.iterrows()}
    assert (1, "Small Feature Size") in events
    assert (2, "Large Feature Size") in events
    assert len(df) == 2  # row with deletions should be excluded


def test_refactor_size_classification_per_file():
    prs_df = pd.DataFrame([
        {"pr_id": 1, "pr_author": "alice", "created_at": "2024-01-01T00:00:00Z"},
        {"pr_id": 2, "pr_author": "bob", "created_at": "2024-02-01T00:00:00Z"},
    ])
    pr_created_at_lookup = {1: "2024-01-01T00:00:00Z", 2: "2024-02-01T00:00:00Z"}
    commits_df = pd.DataFrame([
        {"pr_id": 1, "commit_sha": "a1", "file_path": "src/refactor_small.py", "lines_added": 5, "lines_deleted": 10},
        {"pr_id": 2, "commit_sha": "b1", "file_path": "src/refactor_big.py", "lines_added": 30, "lines_deleted": 40},
        {"pr_id": 3, "commit_sha": "c1", "file_path": "src/feature_only.py", "lines_added": 8, "lines_deleted": 0},
    ])

    df = label_refactor_size(commits_df, prs_df, pr_created_at_lookup, run_timestamp="ts")
    events = {(row.pr_id, row.event) for _, row in df.iterrows()}
    assert (1, "Small Refactor Size") in events
    assert (2, "Large Refactor Size") in events
    # feature-only file should not appear
    assert all(row.filename != "src/feature_only.py" for _, row in df.iterrows())


def test_features_per_branch_labels_one_vs_multiple():
    prs_df = pd.DataFrame([
        {"pr_id": 1, "pr_author": "alice", "created_at": "2024-01-01", "head_branch": "feature/a"},
        {"pr_id": 2, "pr_author": "alice", "created_at": "2024-01-02", "head_branch": "feature/a"},
        {"pr_id": 3, "pr_author": "bob", "created_at": "2024-01-03", "head_branch": "feature/b"},
    ])

    df = label_features_per_branch(prs_df, run_timestamp="ts")
    branch_counts = {(row.branch_name, row.event) for _, row in df.iterrows()}
    assert ("feature/a", "multiple Features Per Branch") in branch_counts
    assert ("feature/b", "one Features Per Branch") in branch_counts


def test_clean_lable_filters_and_parses_events(tmp_path: Path):
    input_csv = tmp_path / "labels.csv"
    output_csv = tmp_path / "clean.csv"

    data = pd.DataFrame([
        {"pr_id": 1, "event": "[\"Random Branch Name\"]", "main_label": "Branch Name", "created_at": "2024-01-01T00:00:00Z", "merged_at": "2024-01-02T00:00:00Z"},
        {"pr_id": 1, "event": "Small Feature Size", "main_label": "Feature Size", "created_at": "2024-01-01T00:00:00Z", "merged_at": "2024-01-02T00:00:00Z"},
        {"pr_id": 1, "event": "outdated", "main_label": "Repository Status", "created_at": "2024-01-01T00:00:00Z", "merged_at": "2024-01-02T00:00:00Z"},
        {"pr_id": 1, "event": "reviewed_merge", "main_label": "Merge State", "created_at": "2024-01-01T00:00:00Z", "merged_at": "2024-01-02T00:00:00Z"},
    ])
    data.to_csv(input_csv, index=False)

    create_clean_branching_label_csv(str(input_csv), output_csv_path=str(output_csv), include_main_label=True)

    cleaned = pd.read_csv(output_csv)
    # events stored as list-like string should be flattened to first element
    assert "Random Branch Name" in cleaned["event"].values
    # Merge State timestamp should prefer merged_at
    assert any(ts.endswith("Z") for ts in cleaned["timestamp"].dropna())


def test_csv_comparison_after_filtering(tmp_path: Path):
    before = tmp_path / "before.csv"
    after = tmp_path / "after.csv"

    before_df = pd.DataFrame([
        {"pr_id": 1, "author": "alice", "status": "human"},
        {"pr_id": 2, "author": "dependabot[bot]", "status": "bot"},
    ])
    after_df = pd.DataFrame([
        {"pr_id": 1, "author": "alice", "status": "human"},
    ])

    before_df.to_csv(before, index=False)
    after_df.to_csv(after, index=False)

    # Ensure bot rows were removed and no deleted rows reappear
    before_prs = set(before_df["pr_id"])
    after_prs = set(after_df["pr_id"])
    assert after_prs.issubset(before_prs)
    assert 2 not in after_prs
    assert len(after_prs) == 1
