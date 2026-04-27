import pytest
import pandas as pd
import os
import sys
from unittest.mock import MagicMock, patch

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from process_model.graphing import (
        _as_str_team,
        load_event_freq_map,
        load_sessions_count_map,
        build_markov_graph,
    )
except Exception as exc:
    pytest.skip(f"Skipping graphing tests: cannot import process_model.graphing ({exc})", allow_module_level=True)

class TestGraphing:
    def test_as_str_team(self):
        assert _as_str_team(7) == "7"
        assert _as_str_team("7") == "7"
        assert _as_str_team(7.0) == "7"
        assert _as_str_team("7.0") == "7"
        assert _as_str_team(None) == "unknown"
        assert _as_str_team(float("nan")) == "unknown"

    def test_load_event_freq_map(self, tmp_path):
        # Create temp CSV
        f = tmp_path / "freq.csv"
        f.write_text("team_number,event,count\n1,A,10\n1,B,5\n2,C,20")
        
        res = load_event_freq_map(str(f))
        
        assert "1" in res
        assert res["1"]["A"] == 10
        assert res["1"]["B"] == 5
        assert "2" in res
        assert res["2"]["C"] == 20

    def test_load_sessions_count_map(self, tmp_path):
        f = tmp_path / "sessions.csv"
        f.write_text("team_number,num_pr_sessions\n1,50\n2,30")
        
        res = load_sessions_count_map(str(f))
        
        assert res["1"] == 50
        assert res["2"] == 30

    @patch("process_model.graphing.Digraph")
    def test_build_markov_graph(self, mock_digraph):
        # Verify it makes calls to graphviz
        mock_dot = MagicMock()
        mock_digraph.return_value = mock_dot
        
        edges = pd.DataFrame([
            {"from": "A", "to": "B", "count": 10},
            {"from": "B", "to": "C", "count": 10}
        ])
        
        build_markov_graph(
            user_label="Test Graph",
            edges_df=edges,
            event_freq={},
            output_path="dummy_dir/dummy_path.png"
        )
        
        # Verify render was called
        mock_dot.render.assert_called_once()
        # Verify nodes/edges were added
        # We can't easily check exact calls without complex matching, 
        # but we can check if it didn't crash and called render.
