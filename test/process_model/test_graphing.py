import pytest
import math
import pandas as pd
import networkx as nx
import os
import sys
from unittest.mock import MagicMock, patch

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.graphing import (
    _as_str_team,
    load_event_freq_map,
    load_sessions_count_map,
    build_markov_graph,
    build_edge_idf_map,
    score_team_edges,
    prune_team_edges_distinctive,
    repair_connectivity,
    fix_orphans,
    _DSU,
)


class TestGraphing:
    def test_as_str_team(self):
        assert _as_str_team(7) == "7"
        assert _as_str_team("7") == "7"
        assert _as_str_team(7.0) == "7"
        assert _as_str_team("7.0") == "7"
        assert _as_str_team(None) == "unknown"
        assert _as_str_team(float("nan")) == "unknown"

    def test_load_event_freq_map(self, tmp_path):
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
        mock_dot.render.assert_called_once()


# =============================================================================
# Helpers
# =============================================================================

def _make_graph(edges):
    """Build nx.DiGraph from (u, v, weight) tuples with prob computed."""
    G = nx.DiGraph()
    for u, v, w in edges:
        G.add_edge(str(u), str(v), weight=float(w), prob=0.0)
    for u in G.nodes():
        total = sum(G[u][x]["weight"] for x in G.successors(u))
        for x in G.successors(u):
            G[u][x]["prob"] = G[u][x]["weight"] / total if total else 0.0
    return G


def _make_teams_df(teams_edges):
    """Build a multi-team DataFrame from {team_id: [(u, v, count), ...]}."""
    rows = []
    for team, edges in teams_edges.items():
        for u, v, c in edges:
            rows.append({"team_number": str(team), "from": str(u),
                         "to": str(v), "count": c})
    return pd.DataFrame(rows)


# =============================================================================
# TestIdfPruning -- 4 required tests
# =============================================================================

class TestIdfPruning:
    """
    Tests for the cross-team IDF distinctiveness pruning pipeline.
    """

    # ------------------------------------------------------------------
    # Test 1: shared edge gets lower IDF; unique edge higher IDF and kept
    # ------------------------------------------------------------------
    def test_shared_edge_lower_idf_unique_edge_kept(self):
        """
        Two teams. Edge A->B appears in both (df=2, low IDF).
        Edge A->C appears only in Team 1 (df=1, high IDF).

        For Team 1 (top_k=1), score = prob * idf.
        A->C wins because higher IDF lifts its score above A->B
        even though both have the same raw count.
        """
        teams_df = _make_teams_df({
            "1": [("A", "B", 5), ("A", "C", 5)],
            "2": [("A", "B", 5)],
        })
        idf_map, N = build_edge_idf_map(teams_df, min_count=2)
        assert N == 2

        # A->B present in 2 teams: idf = log(3/3)+1 = 1.0
        # A->C present in 1 team:  idf = log(3/2)+1 > 1.0
        idf_ab = idf_map.get(("A", "B"), 1.0)
        idf_ac = idf_map.get(("A", "C"), 1.0)
        assert idf_ab == pytest.approx(math.log(3 / 3) + 1, rel=1e-6)
        assert idf_ac > idf_ab

        # Score Team 1's graph -- A->C must outscore A->B
        G = _make_graph([("A", "B", 5), ("A", "C", 5)])
        scores = score_team_edges(G, idf_map, strength_mode="prob")
        assert scores[("A", "C")] > scores[("A", "B")]

        # top_k=1: only A->C kept (higher score)
        keep = prune_team_edges_distinctive(G, scores, top_k=1)
        assert ("A", "C") in keep
        assert ("A", "B") not in keep

    # ------------------------------------------------------------------
    # Test 2: connectivity repair reconnects components with best bridge
    # ------------------------------------------------------------------
    def test_connectivity_repair_reconnects_with_best_bridge(self):
        """
        After Pass 1, two clusters are disconnected.
        Pass 2 adds the highest-score bridge to reconnect.

        Cluster LEFT:  S->A (high score kept), S->B (pruned)
                       A->Z (A's top-1, kept -- keeps A from being dead end)
                       A->Y (pruned -- bridge candidate, score=0.1)
        Cluster RIGHT: X->Y (kept as top-1 of X)
        Bridge:        S->X (score=0.3, best bridge)
        """
        G = _make_graph([
            ("S", "A", 100), ("S", "B", 1),
            ("A", "Z", 60),  ("A", "Y", 5),
            ("X", "Y", 80),  ("X", "W", 2),
            ("S", "X", 30),
        ])

        # Assign IDF so S->X has a high score as a bridge candidate
        idf_map = {("S", "X"): 2.0, ("A", "Y"): 1.1}
        scores = score_team_edges(G, idf_map, strength_mode="prob")

        # Pass 1: keep top-1 per source
        keep = prune_team_edges_distinctive(G, scores, top_k=1)

        # Pass 2: best bridge S->X should be added
        all_nodes = set(G.nodes())
        keep, n_before, n_after, bridges = repair_connectivity(
            keep, G, scores, all_nodes
        )
        assert ("S", "X") in keep
        assert n_after <= n_before  # components can only shrink

    # ------------------------------------------------------------------
    # Test 3: orphan fix restores incident edge for isolated node
    # ------------------------------------------------------------------
    def test_orphan_fix_restores_incident_edge(self):
        """
        Node O is only reachable via A->O (weak, pruned in Pass 1).
        A->C is kept (top-1 of A). O becomes orphaned.
        Pass 3 must restore A->O so O has at least one incident edge.
        """
        G = _make_graph([
            ("S", "A", 100), ("S", "B", 1),
            ("A", "C", 80),  ("A", "O", 2),
        ])
        idf_map = {}   # neutral IDF
        scores = score_team_edges(G, idf_map, strength_mode="prob")

        keep = prune_team_edges_distinctive(G, scores, top_k=1)
        # O should not appear in kept edges after Pass 1
        incident_p1 = {n for edge in keep for n in edge}
        assert "O" not in incident_p1

        # Pass 3
        all_nodes = set(G.nodes())
        keep, fixes = fix_orphans(keep, G, scores, all_nodes)
        assert fixes >= 1
        incident_p3 = {n for edge in keep for n in edge}
        assert "O" in incident_p3

    # ------------------------------------------------------------------
    # Test 4: full pipeline is deterministic across multiple calls
    # ------------------------------------------------------------------
    def test_deterministic_output(self):
        """
        Multiple calls with identical input must produce identical keep_set.
        Validates sorted(G.nodes(), key=str), IDF scoring, and all
        sort keys in bridge/orphan selection.
        """
        G = _make_graph([
            ("S", "A", 100), ("S", "B", 5), ("S", "C", 5),
            ("X", "Y", 80),  ("X", "Z", 3),
            ("S", "X", 30),  ("A", "Y", 10),
        ])
        idf_map = {("S", "A"): 1.4, ("X", "Y"): 1.4, ("S", "X"): 1.2}
        scores = score_team_edges(G, idf_map, strength_mode="prob")
        all_nodes = set(G.nodes())

        def full_pipeline():
            keep = prune_team_edges_distinctive(G, scores, top_k=1)
            keep, *_ = repair_connectivity(keep, G, scores, all_nodes)
            keep, _ = fix_orphans(keep, G, scores, all_nodes)
            return frozenset(keep)

        r1 = full_pipeline()
        r2 = full_pipeline()
        r3 = full_pipeline()
        assert r1 == r2 == r3
