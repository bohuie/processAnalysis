import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.clustering import build_team_matrix, choose_best_k

class TestClustering:
    def test_build_team_matrix(self):
        # Setup mock data
        data = {
            "team_number": ["1", "1", "2", "2"],
            "from": ["A", "B", "A", "C"],
            "to": ["B", "C", "C", "D"],
            "count": [10, 5, 8, 3],
            "z_score": [2.0, 2.0, 2.0, 1.5] # One below threshold
        }
        df = pd.DataFrame(data)
        
        # Test with threshold 1.6
        teams, pairs, X = build_team_matrix(df, z_threshold=1.6)
        
        assert "1" in teams
        assert "2" in teams
        assert len(teams) == 2
        
        # Check pairs - sorted unique pairs from FULL df (even filtered out ones? 
        # The logic in build_team_matrix says: pairs = sorted(set(zip(df["from"], df["to"])))
        # But wait, it copies df first, THEN defines pairs. So pairs comes from the unfiltered df.
        # Actually in the code:
        # df = df.copy()
        # pairs = sorted(set(zip(df["from"], df["to"])))
        # ...
        # if "z_score" in df.columns: df = df[df["z_score"] >= z_threshold]
        
        # So yes, pairs includes all pairs from input df.
        expected_pairs = sorted([("A", "B"), ("B", "C"), ("A", "C"), ("C", "D")])
        assert pairs == expected_pairs
        
        # Convert X to dict for easier checking
        # teams are sorted: "1", "2"
        # pairs are sorted
        
        # Team 1: A->B (10), B->C (5)
        # Team 2: A->C (8), C->D (3 is filtered out because z=1.5 < 1.6) -> Wait.
        # The filtering happens on the rows.
        # For team 2, the row C->D has z=1.5. If threshold is 1.6, this row is removed.
        # So Team 2 should NOT have the count for C->D.
        
        t1_idx = teams.index("1")
        t2_idx = teams.index("2")
        
        ab_idx = pairs.index(("A", "B"))
        cd_idx = pairs.index(("C", "D"))
        
        assert X[t1_idx, ab_idx] == 10.0
        assert X[t2_idx, cd_idx] == 0.0 # Should be zero because it was filtered

    def test_choose_best_k(self):
        # Create clear clusters
        # Cluster 1: [1, 1], [1.1, 1.1], [0.9, 0.9]
        # Cluster 2: [10, 10], [10.1, 10.1], [9.9, 9.9]
        X = np.array([
            [1, 1], [1.1, 1.1], [0.9, 0.9],
            [10, 10], [10.1, 10.1], [9.9, 9.9]
        ])
        
        best_k, best_score = choose_best_k(X, k_min=2, k_max=5)
        assert best_k == 2
        assert best_score > 0.5 # Should be good separation

    def test_choose_best_k_small_n(self):
        X = np.array([[1,1], [2,2]])
        best_k, _ = choose_best_k(X)
        assert best_k == 2 # Function returns 2 if n < 3
