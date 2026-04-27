import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.markov_common import (
    normalize_event_field,
    compute_overall_edges as compute_overall_edges_old_style,
    compute_avg_session_edges as compute_avg_session_edges_old_style,
    add_transition_probs,
)

class TestTransitionEdges:
    def test_normalize_event_field(self):
        # String
        assert normalize_event_field("foobar") == ["foobar"]
        # List string
        assert normalize_event_field("['a', 'b']") == ["a", "b"]
        assert normalize_event_field('["a", "b"]') == ["a", "b"]
        # Actual list
        assert normalize_event_field(["a", "b"]) == ["a", "b"]
        # Empty
        assert normalize_event_field(None) == []
        assert normalize_event_field("") == []
        assert normalize_event_field("[]") == []

    def test_compute_overall_edges_old_style(self):
        # Setup: 2 PR sessions
        # PR 1: A -> B -> C
        # PR 2: A -> B
        
        # Expected edges: (A,B): 2, (B,C): 1
        
        data = {
            "pr_id": [1, 1, 1, 2, 2],
            "event": ["A", "B", "C", "A", "B"]
        }
        df = pd.DataFrame(data)
        
        edges, n_sessions = compute_overall_edges_old_style(df)
        
        assert n_sessions == 2
        
        # Convert to easy lookup
        lookup = {(r["from"], r["to"]): r["count"] for _, r in edges.iterrows()}
        
        assert lookup.get(("A", "B")) == 2
        assert lookup.get(("B", "C")) == 1
        assert len(lookup) == 2

    def test_compute_avg_session_edges_old_style(self):
        # Setup: 2 PR sessions
        # PR 1: A -> B (Sequence: START -> A -> B -> END)
        # PR 2: A (Sequence: START -> A -> END)
        
        # Edges pooled:
        # START->A: 2
        # A->B: 1
        # B->END: 1
        # A->END: 1
        
        # Avg = Count / n_sessions
        # START->A: 2/2 = 1.0
        # A->B: 1/2 = 0.5
        # B->END: 1/2 = 0.5
        # A->END: 1/2 = 0.5
        
        data = {
            "pr_id": [1, 1, 2],
            "event": ["A", "B", "A"]
        }
        df = pd.DataFrame(data)
        
        edges = compute_avg_session_edges_old_style(df, n_sessions=2)
        
        lookup = {(r["from"], r["to"]): r["count"] for _, r in edges.iterrows()}
        
        assert lookup.get(("START", "A")) == 1.0
        assert lookup.get(("A", "B")) == 0.5
        assert lookup.get(("B", "END")) == 0.5
        assert lookup.get(("A", "END")) == 0.5

    def test_add_transition_probs(self):
        # A -> B (10)
        # A -> C (30)
        # Total from A = 40
        # Prob(A->B) = 0.25
        # Prob(A->C) = 0.75
        
        data = {
            "from": ["A", "A", "B"],
            "to": ["B", "C", "D"],
            "count": [10, 30, 5]
        }
        df = pd.DataFrame(data)
        
        res = add_transition_probs(df)
        
        ab = res[(res["from"] == "A") & (res["to"] == "B")].iloc[0]
        ac = res[(res["from"] == "A") & (res["to"] == "C")].iloc[0]
        
        assert ab["prob"] == 0.25
        assert ac["prob"] == 0.75
        
        bd = res[(res["from"] == "B") & (res["to"] == "D")].iloc[0]
        assert bd["prob"] == 1.0
