import pandas as pd

from event_labelling.CodeStructure_Branching.label_features_per_branch import (
    label_features_per_branch,
)
from event_labelling.CodeStructure_Branching.label_pr_status import label_pr_status
from src.utils.markov_common import compute_overall_edges as compute_overall_edges_old_style


def edge_count(edges_df: pd.DataFrame, src: str, dst: str) -> float:
    match = edges_df[(edges_df["from"] == src) & (edges_df["to"] == dst)]
    if match.empty:
        return 0
    return float(match.iloc[0]["count"])


def test_same_branch_used_by_two_related_prs_inflates_pooled_transitions():
    """
    Two related PRs reuse the same branch/logical work.
    The branch-level label is emitted for both PRs, then each PR contributes its own
    transition sequence to the pooled Markov edges.
    """
    prs_df = pd.DataFrame(
        [
            {
                "pr_id": 101,
                "pr_author": "alice",
                "head_branch": "feature/auth-flow",
                "created_at": "2026-01-01T10:00:00Z",
                "state": "closed",
                "merged_at": "2026-01-01T11:00:00Z",
            },
            {
                "pr_id": 102,
                "pr_author": "alice",
                "head_branch": "feature/auth-flow",
                "created_at": "2026-01-02T10:00:00Z",
                "state": "closed",
                "merged_at": "2026-01-02T11:00:00Z",
            },
        ]
    )

    run_timestamp = "2026-03-09T00:00:00Z"

    branch_df = label_features_per_branch(prs_df, run_timestamp)
    status_df = label_pr_status(prs_df, run_timestamp)

    # Keep only the columns transition_edges needs
    combined = pd.concat(
        [
            branch_df[["pr_id", "created_at", "event"]].rename(columns={"created_at": "timestamp"}),
            status_df[["pr_id", "created_at", "event"]].rename(columns={"created_at": "timestamp"}),
        ],
        ignore_index=True,
    ).sort_values(["pr_id", "timestamp"]).reset_index(drop=True)

    overall_edges, n_sessions = compute_overall_edges_old_style(combined)

    # Two PR ids => two sessions
    assert n_sessions == 2

    # Since both PRs share the same branch, both get the same branch-level event:
    # "multiple Features Per Branch"
    # Each PR also gets "merged", so the pooled edge count becomes 2.
    assert edge_count(overall_edges, "multiple Features Per Branch", "merged") == 2