import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.zscore_calculation import zscore_per_team

class TestZScoreCalculation:
    def test_zscore_per_team_normal(self):
        # Setup data: Team 1 has counts 10, 20, 30. Mean=20, Std (ddof=0) = sqrt((100+0+100)/3) = sqrt(66.66) = 8.16
        # Team 2 has counts 5, 5. Mean=5, Std=0.
        
        data = {
            "team_number": ["1", "1", "1", "2", "2"],
            "from": ["A", "B", "C", "X", "Y"],
            "to": ["B", "C", "D", "Y", "Z"],
            "count": [10, 20, 30, 5, 5]
        }
        df = pd.DataFrame(data)
        
        res = zscore_per_team(df, "team_number")
        
        # Check Team 1 z-scores
        t1 = res[res["team_number"] == "1"]
        assert len(t1) == 3
        # z = (x - mean) / std
        # (10-20)/8.16 = -1.22
        # (20-20)/8.16 = 0
        # (30-20)/8.16 = 1.22
        
        # approximate check
        counts = t1["count"].astype(float).values
        zscores = t1["z_score"].values
        mean = counts.mean()
        std = counts.std(ddof=0)
        
        expected = (counts - mean) / std
        np.testing.assert_allclose(zscores, expected, rtol=1e-5)
        
        # Check Team 2 z-scores (std=0 case)
        t2 = res[res["team_number"] == "2"]
        assert (t2["z_score"] == 0.0).all()

    def test_zscore_empty_or_single(self):
        data = {
            "team_number": ["1"],
            "from": ["A"],
            "to": ["B"],
            "count": [10]
        }
        df = pd.DataFrame(data)
        res = zscore_per_team(df, "team_number")
        # Single value -> std=0 -> z_score=0
        assert res.iloc[0]["z_score"] == 0.0
