import pandas as pd

from process_model.transition_edges import load_noholes_csv
from src.utils.markov_common import (
    compute_overall_edges as compute_overall_edges_old_style,
    compute_avg_session_edges as compute_avg_session_edges_old_style,
)


def edge_count(edges_df: pd.DataFrame, src: str, dst: str) -> float:
    match = edges_df[(edges_df["from"] == src) & (edges_df["to"] == dst)]
    if match.empty:
        return 0
    return float(match.iloc[0]["count"])


def test_related_prs_with_same_logical_sequence_are_counted_twice(tmp_path):
    """
    Simulates the semantic double-counting case:
    PR 101 = feature/A -> dev
    PR 102 = dev -> main

    Even if they represent the same underlying work, the process model keys by pr_id,
    so both sessions contribute the same transitions.
    """
    df = pd.DataFrame(
        [
            {"pr_id": 101, "timestamp": "2026-01-01T10:00:00Z", "event": "Meaningful Branch Name"},
            {"pr_id": 101, "timestamp": "2026-01-01T10:01:00Z", "event": "merged"},
            {"pr_id": 102, "timestamp": "2026-01-02T10:00:00Z", "event": "Meaningful Branch Name"},
            {"pr_id": 102, "timestamp": "2026-01-02T10:01:00Z", "event": "merged"},
        ]
    )

    fp = tmp_path / "clean_labels.csv"
    df.to_csv(fp, index=False)

    loaded = load_noholes_csv(fp)
    overall_edges, n_sessions = compute_overall_edges_old_style(loaded)
    avg_edges = compute_avg_session_edges_old_style(loaded, n_sessions=n_sessions)

    # Two PRs => two separate sessions
    assert n_sessions == 2

    # Same transition appears once per PR, so pooled count becomes 2
    assert edge_count(overall_edges, "Meaningful Branch Name", "merged") == 2

    # Avg-session graph divides pooled count by number of sessions: 2 / 2 = 1
    assert edge_count(avg_edges, "Meaningful Branch Name", "merged") == 1.0