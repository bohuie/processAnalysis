import pytest
import math
import pandas as pd
import networkx as nx
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from process_model.graphing import (
    _as_str_team,
    load_event_freq_map,
    load_sessions_count_map,
    build_markov_graph,
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


# =============================================================================
# TestConnectivityRepair -- structural guarantee tests (Pass 2 + 3)
# =============================================================================

class TestConnectivityRepair:
    """
    Tests for repair_connectivity (Pass 2) and fix_orphans (Pass 3).
    These are weight-based, pipeline-agnostic structural guarantees.
    """

    # ------------------------------------------------------------------
    # Test 1: repair_connectivity reconnects two disjoint components
    # ------------------------------------------------------------------
    def test_repair_connects_two_components(self):
        """
        Graph has two disconnected clusters: {S, A} and {X, Y}.
        Only edges within each cluster are in keep_set initially.
        repair_connectivity must add the highest-weight bridge S->X.
        """
        G = _make_graph([
            ("S", "A", 100),
            ("X", "Y", 80),
            ("S", "X", 30),   # bridge
        ])
        # Start with only within-cluster edges
        keep_set = {("S", "A"), ("X", "Y")}
        all_nodes = set(G.nodes())

        keep_set, n_before, n_after, bridges = repair_connectivity(keep_set, G, all_nodes)

        assert n_before > 1, "expected 2 components before repair"
        assert n_after == 1, "expected 1 component after repair"
        assert ("S", "X") in keep_set
        assert bridges >= 1

    # ------------------------------------------------------------------
    # Test 2: repair_connectivity is a no-op when already connected
    # ------------------------------------------------------------------
    def test_repair_noop_when_connected(self):
        """
        If all nodes are already in one component, no edges should be added.
        """
        G = _make_graph([("A", "B", 10), ("B", "C", 5)])
        keep_set = {("A", "B"), ("B", "C")}
        all_nodes = set(G.nodes())

        keep_set, n_before, n_after, bridges = repair_connectivity(keep_set, G, all_nodes)

        assert n_before == 1
        assert n_after == 1
        assert bridges == 0

    # ------------------------------------------------------------------
    # Test 3: fix_orphans restores incident edge for isolated node
    # ------------------------------------------------------------------
    def test_fix_orphans_restores_isolated_node(self):
        """
        Node O is not in any kept edge. fix_orphans must restore its
        strongest incident edge.
        """
        G = _make_graph([
            ("S", "A", 100),
            ("A", "O", 5),    # O is orphaned in keep_set
        ])
        keep_set = {("S", "A")}
        all_nodes = set(G.nodes())

        keep_set, fixes = fix_orphans(keep_set, G, all_nodes)

        assert fixes >= 1
        incident = {n for edge in keep_set for n in edge}
        assert "O" in incident

    # ------------------------------------------------------------------
    # Test 4: fix_orphans is a no-op when there are no orphans
    # ------------------------------------------------------------------
    def test_fix_orphans_noop_when_none(self):
        """All nodes appear in keep_set -- no fixes needed."""
        G = _make_graph([("A", "B", 10), ("B", "C", 5)])
        keep_set = {("A", "B"), ("B", "C")}
        all_nodes = set(G.nodes())

        keep_set, fixes = fix_orphans(keep_set, G, all_nodes)
        assert fixes == 0

    # ------------------------------------------------------------------
    # Test 5: full pipeline (Pass 2 + 3) is deterministic
    # ------------------------------------------------------------------
    def test_full_pipeline_deterministic(self):
        """Multiple runs with identical input must produce identical output."""
        G = _make_graph([
            ("S", "A", 100), ("S", "B", 5), ("S", "C", 5),
            ("X", "Y", 80),  ("X", "Z", 3),
            ("S", "X", 30),  ("A", "Y", 10),
        ])
        all_nodes = set(G.nodes())

        def full_pipeline():
            keep = set(G.edges())           # start: all edges (as filtered upstream)
            keep, *_ = repair_connectivity(keep, G, all_nodes)
            keep, _  = fix_orphans(keep, G, all_nodes)
            return frozenset(keep)

        r1 = full_pipeline()
        r2 = full_pipeline()
        r3 = full_pipeline()
        assert r1 == r2 == r3
