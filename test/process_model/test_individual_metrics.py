import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.individual_metrics import (
    normalize_event_field,
    safe_rate,
    compute_dev_metrics
)

class TestIndividualMetrics:
    def test_normalize_event_field(self):
        # Plain string
        assert normalize_event_field("Meaningful Branch Name") == ["Meaningful Branch Name"]
        
        # Stringified list
        assert normalize_event_field("['a', 'b']") == ["a", "b"]
        assert normalize_event_field('["x", "y"]') == ["x", "y"]
        
        # Actual list
        assert normalize_event_field(["c", "d"]) == ["c", "d"]
        
        # Empty/NaN
        assert normalize_event_field(None) == []
        assert normalize_event_field(pd.NA) == []
        assert normalize_event_field("") == []
        assert normalize_event_field("[]") == []

    def test_safe_rate(self):
        assert safe_rate(5, 10) == 0.5
        assert safe_rate(1, 3) == 0.3333
        assert safe_rate(0, 5) == 0.0
        assert safe_rate(5, 0) == 0.0

    def test_compute_dev_metrics(self):
        # Create dummy events for a single developer
        data = {
            "pr_id": [1, 1, 1, 2, 2, 3],
            "timestamp": pd.to_datetime([
                "2023-01-01T10:00:00Z", "2023-01-01T10:05:00Z", "2023-01-01T10:10:00Z",
                "2023-01-02T10:00:00Z", "2023-01-02T10:05:00Z",
                "2023-01-03T10:00:00Z"
            ]),
            "event": [
                "Meaningful Branch Name", "self_merge", "END",
                "Meaningful Branch Name", "reviewed_merge",
                "outdated"
            ]
        }
        df = pd.DataFrame(data)

        metrics = compute_dev_metrics(df)

        # Basic counts
        assert metrics["num_prs"] == 3
        assert metrics["total_labels"] == 6
        assert metrics["unique_labels"] == 5
        
        # We had Meaningful Branch Name twice (in 2 PRs)
        assert metrics["meaningful_branch_rate"] == 0.6667 # 2 / 3
        assert metrics["self_merge_rate"] == 0.3333 # 1 / 3
        assert metrics["reviewed_merge_rate"] == 0.3333 # 1 / 3
        assert metrics["outdated_rate"] == 0.3333 # 1 / 3
        assert metrics["pr_description_clear_rate"] == 0.0
        
        # Transitions
        # PR 1 transitions: Meaningful Branch Name -> self_merge -> END (2 transitions)
        # PR 2 transitions: Meaningful Branch Name -> reviewed_merge (1 transition)
        # PR 3 transitions: no transitions (only 1 event)
        assert metrics["total_transitions"] == 3
        assert metrics["unique_transitions"] == 3
        assert metrics["avg_transitions_per_pr"] == 1.0 # 3 total / 3 PRs

        # Top transition: all appear once, Python max will pick one. Probability is count / from_total.
        assert metrics["top_transition_prob"] == 0.5  # If Meaningful Branch Name -> ... is picked, from_total is 2, count is 1.

        # First/Last labels
        # First events: Meaningful, Meaningful, outdated -> Meaningful
        assert metrics["most_common_first_label"] == "Meaningful Branch Name"
        # Last events: END, reviewed_merge, outdated -> END, reviewed_merge, or outdated
        # value_counts will choose one arbitrarily since they are all 1
        assert metrics["most_common_last_label"] in ["END", "reviewed_merge", "outdated"]
