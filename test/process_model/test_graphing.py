import pytest
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
    prune_edges_by_zscore,
    prune_edges_connectivity_preserving,
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


# =============================================================================
# Unit tests for prune_edges_by_zscore
# =============================================================================

def _make_graph(edges: list[tuple]) -> nx.DiGraph:
    """Helper: build a DiGraph from (u, v, weight) tuples."""
    G = nx.DiGraph()
    for u, v, w in edges:
        G.add_edge(u, v, weight=float(w))
    return G


class TestPruneEdgesByZScore:
    # ------------------------------------------------------------------
    # Case 1: sigma == 0  (all outgoing weights identical)
    # ------------------------------------------------------------------
    def test_sigma_zero_keeps_only_top_k(self):
        """
        Node A has 3 outgoing edges all with weight=5.
        sigma == 0, so z is undefined.  Only the top-K edge (alphabetically
        first target when weights tie) must be kept.
        """
        G = _make_graph([
            ("A", "B", 5),
            ("A", "C", 5),
            ("A", "D", 5),
        ])
        kept = prune_edges_by_zscore(G, z_min=1.0, top_k=1)

        # With sigma==0 only top-K survives. Tie-break: asc target name → "B"
        assert ("A", "B") in kept
        assert ("A", "C") not in kept
        assert ("A", "D") not in kept

    def test_sigma_zero_top_k_two(self):
        """top_k=2 keeps the two alphabetically-first targets when weights tie."""
        G = _make_graph([
            ("A", "X", 10),
            ("A", "Y", 10),
            ("A", "Z", 10),
        ])
        kept = prune_edges_by_zscore(G, z_min=1.0, top_k=2)

        assert ("A", "X") in kept
        assert ("A", "Y") in kept
        assert ("A", "Z") not in kept

    # ------------------------------------------------------------------
    # Case 2: single outgoing edge — always kept
    # ------------------------------------------------------------------
    def test_single_outgoing_edge_always_kept(self):
        """
        A node with only 1 outgoing edge must always be kept, regardless of
        z_min, because min_out_edges_to_zscore=2 and top_k=1 both guarantee it.
        """
        G = _make_graph([("START", "A", 3)])
        kept = prune_edges_by_zscore(G, z_min=99.0, top_k=1)

        # The single edge must survive even with a huge z_min threshold.
        assert ("START", "A") in kept

    def test_single_outgoing_edge_no_extras_created(self):
        """Return set must never contain edges that do not exist in G."""
        G = _make_graph([("START", "A", 3)])
        kept = prune_edges_by_zscore(G, z_min=0.0, top_k=1)

        assert kept == {("START", "A")}

    # ------------------------------------------------------------------
    # Case 3: standout edge kept by z-score + top-K fallback
    # ------------------------------------------------------------------
    def test_standout_edge_kept_weak_edges_pruned(self):
        """
        Node S has four outgoing edges:
          S→A  weight=1  (low)
          S→B  weight=2  (low)
          S→C  weight=3  (medium)
          S→D  weight=100 (standout — very high z-score)

        With z_min=1.0 and top_k=1:
          • S→D has a large positive z → kept by z-score rule.
          • S→D is also top-1 by weight.
          • S→A, S→B, S→C have negative z (below mean) → pruned, and
            none of them are in top-1.

        Expected keep set: {(S, D)}
        """
        G = _make_graph([
            ("S", "A", 1),
            ("S", "B", 2),
            ("S", "C", 3),
            ("S", "D", 100),
        ])
        kept = prune_edges_by_zscore(G, z_min=1.0, top_k=1)

        assert ("S", "D") in kept
        assert ("S", "A") not in kept
        assert ("S", "B") not in kept
        assert ("S", "C") not in kept

    def test_top_k_fallback_preserves_node_connectivity(self):
        """
        Even if NO edge passes the z_min threshold, top_k=1 guarantees the
        highest-weight edge survives, so the source node is never isolated.
        """
        # All weights the same except one slightly higher — but z_min is huge.
        G = _make_graph([
            ("S", "A", 5),
            ("S", "B", 6),   # highest weight → top-1
            ("S", "C", 4),
        ])
        # z_min=999 means z-score rule keeps nothing; top_k=1 must rescue top edge.
        kept = prune_edges_by_zscore(G, z_min=999.0, top_k=1)

        assert ("S", "B") in kept          # top-1 by weight
        assert ("S", "A") not in kept
        assert ("S", "C") not in kept

    # ------------------------------------------------------------------
    # Case 4: ties in weight handled deterministically
    # ------------------------------------------------------------------
    def test_tie_breaking_is_deterministic_by_target_name(self):
        """
        When multiple edges share the same top weight, top-K selection must
        be deterministic.  Tie-break rule: ascending target node name (str).

        S→"alpha"  weight=10
        S→"beta"   weight=10   ← both tied; "alpha" < "beta" alphabetically
        S→"gamma"  weight=5

        top_k=1 → should keep S→"alpha" (first alphabetically among ties).
        """
        G = _make_graph([
            ("S", "alpha", 10),
            ("S", "beta",  10),
            ("S", "gamma",  5),
        ])
        kept = prune_edges_by_zscore(G, z_min=999.0, top_k=1)

        assert ("S", "alpha") in kept
        assert ("S", "beta")  not in kept
        assert ("S", "gamma") not in kept

    def test_tie_breaking_top_k_two(self):
        """top_k=2 with a three-way weight tie picks the two alphabetically first."""
        G = _make_graph([
            ("S", "zebra", 10),
            ("S", "ant",   10),
            ("S", "cat",   10),
        ])
        kept = prune_edges_by_zscore(G, z_min=999.0, top_k=2)

        # Alphabetical ascending: ant < cat < zebra → keep ant and cat.
        assert ("S", "ant")   in kept
        assert ("S", "cat")   in kept
        assert ("S", "zebra") not in kept

    # ------------------------------------------------------------------
    # Edge-case guards
    # ------------------------------------------------------------------
    def test_no_outgoing_edges_node_ignored(self):
        """A sink node (no outgoing edges) contributes nothing to the keep set."""
        G = _make_graph([("A", "SINK", 5)])
        kept = prune_edges_by_zscore(G, z_min=1.0, top_k=1)

        # SINK has no outgoing edges, A→SINK should still be kept (only 1 out-edge).
        assert ("A", "SINK") in kept
        # No phantom edges invented.
        assert all(u != "SINK" for (u, _) in kept)

    def test_min_out_edges_threshold_bypasses_zscore(self):
        """
        If a node has fewer outgoing edges than min_out_edges_to_zscore,
        ALL its edges are kept regardless of z_min.
        """
        G = _make_graph([("A", "B", 1)])
        # min_out_edges_to_zscore=2 means 1-edge nodes are never z-scored.
        kept = prune_edges_by_zscore(G, z_min=50.0, top_k=1, min_out_edges_to_zscore=2)
        assert ("A", "B") in kept

    def test_never_creates_new_edges(self):
        """The returned keep set must be a subset of G's actual edges."""
        G = _make_graph([
            ("X", "Y", 10),
            ("X", "Z",  1),
            ("Y", "Z",  5),
        ])
        kept = prune_edges_by_zscore(G, z_min=0.0, top_k=2)
        graph_edges = set(G.edges())
        assert kept.issubset(graph_edges)


# =============================================================================
# Unit tests for prune_edges_connectivity_preserving (3-pass)
# =============================================================================

class TestPruneEdgesConnectivityPreserving:
    """
    Tests for the connectivity-preserving 3-pass pruning pipeline.

    Graph topology used as a helper:  _make_graph (defined above in this module)
    builds a nx.DiGraph from (u, v, weight) tuples.
    """

    # ------------------------------------------------------------------
    # Test 1: 2 components after Pass 1 → repair reconnects with best bridge
    # ------------------------------------------------------------------
    def test_repair_reconnects_two_components(self):
        """
        After Pass-1 pruning, the graph splits into two isolated islands.
        Pass-2 must add back the highest-weight bridge to restore connectivity.

        Cluster 1 (LEFT):
          S→A  w=100  ← kept by z-score (standout)
          S→B  w=1    ← pruned
          A→Z  w=60   ← A has 2 out-edges so no keep-all: A→Z kept (top-1 of A)
          A→Y  w=5    ← pruned (low z on A; cross-cluster but NOT kept by pass1)

        Cluster 2 (RIGHT):
          X→Y  w=80   ← kept (top-1 of X since X has only 1 out-edge... actually
                         X has 2 so z-score applies; X→Y is the standout)
          X→W  w=2    ← pruned

        Bridge candidates (not in pass-1 keep_set):
          S→X  w=30   ← best bridge (highest weight cross-cluster edge)
          A→Y  w=5    ← weaker bridge
        """
        G = _make_graph([
            # Cluster 1
            ("S", "A",  100),
            ("S", "B",  1),
            ("A", "Z",  60),   # A has 2 out-edges → z-score applies; Z kept
            ("A", "Y",  5),    # pruned; also a bridge but weaker than S→X
            # Cluster 2
            ("X", "Y",  80),
            ("X", "W",  2),
            # Best bridge between clusters
            ("S", "X",  30),   # not kept by pass1; only cross-cluster edge with w>5
        ])
        kept = prune_edges_connectivity_preserving(G, z_min=1.0, top_k=1)

        # The best bridge is S→X (w=30); A→Y (w=5) is weaker.
        assert ("S", "X") in kept

        # Verify the full graph is weakly connected.
        adj: dict = {}
        for u, v in kept:
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
        from collections import deque
        all_nodes_in_kept = set(adj.keys())
        visited: set = set()
        queue: deque = deque([next(iter(all_nodes_in_kept))])
        while queue:
            n = queue.popleft()
            if n in visited:
                continue
            visited.add(n)
            for nb in adj.get(n, set()):
                if nb not in visited:
                    queue.append(nb)
        assert visited == all_nodes_in_kept


    # ------------------------------------------------------------------
    # Test 2: Orphan node after Pass 1 → orphan fix restores one incident edge
    # ------------------------------------------------------------------
    def test_orphan_fix_restores_incident_edge(self):
        """
        Setup: node 'O' is connected to the rest of the graph only via a weak
        edge that Pass-1 prunes.  Pass-2 may or may not pick it up (here it
        doesn't, because O is a pure sink with no outgoing edge that could be
        a bridge).  Pass-3 must restore O's strongest incident edge.

        Graph:
          S→A  w=100  ← kept by z-score
          S→B  w=1    ← pruned
          A→O  w=2    ← O's only connection; pruned by A's top-1 = A→C
          A→C  w=80   ← kept by z-score (top-1 of A)
        """
        G = _make_graph([
            ("S", "A", 100),
            ("S", "B", 1),
            ("A", "O", 2),
            ("A", "C", 80),
        ])
        kept = prune_edges_connectivity_preserving(G, z_min=1.0, top_k=1)

        # O must appear in kept (via A→O or any incident edge restore).
        incident_nodes = set()
        for u, v in kept:
            incident_nodes.add(u)
            incident_nodes.add(v)
        assert "O" in incident_nodes

    # ------------------------------------------------------------------
    # Test 3: Deterministic tie-breaking when multiple bridges share same weight
    # ------------------------------------------------------------------
    def test_deterministic_bridge_selection_on_tie(self):
        """
        Two equally-weighted bridge edges exist.  The function must always
        pick the same one (alphabetically first by (u, v) string on a tie).

        Graph:
          LEFT side:   L→A  w=50  (kept, top-1 of L)
          RIGHT side:  R→B  w=50  (kept, top-1 of R)
          Bridges:
            L→R  w=10  (alphabetically: 'L','R')
            A→R  w=10  (alphabetically: 'A','R')   ← 'A' < 'L', so 'A→R' sorts first
        """
        G = _make_graph([
            ("L", "A", 50),
            ("R", "B", 50),
            ("L", "R", 10),   # bridge candidate
            ("A", "R", 10),   # bridge candidate (same weight, sorts first)
        ])
        kept1 = prune_edges_connectivity_preserving(G, z_min=1.0, top_k=1)
        kept2 = prune_edges_connectivity_preserving(G, z_min=1.0, top_k=1)

        # Must be identical across two calls (deterministic).
        assert kept1 == kept2

        # The bridge chosen should be A→R because str('A') < str('L').
        assert ("A", "R") in kept1

    # ------------------------------------------------------------------
    # Test 4: Minimality — only (initial_components − 1) bridges added
    # ------------------------------------------------------------------
    def test_minimal_bridges_added(self):
        """
        A Kruskal-style check: to connect K components you need exactly K-1
        bridges.  Verify the function adds the minimum number.

        Graph: 3 isolated pairs (6 nodes, 3 components after Pass 1).
          S1→A1  w=100  (each kept by z-score / top-1)
          S2→A2  w=100
          S3→A3  w=100
          Cross-bridges (all weight=5, not kept by Pass 1):
            A1→S2, A2→S3   ← 2 bridges needed to unify 3 components
        """
        G = _make_graph([
            ("S1", "A1", 100),
            ("S2", "A2", 100),
            ("S3", "A3", 100),
            ("A1", "S2", 5),   # bridge 1
            ("A2", "S3", 5),   # bridge 2
        ])
        kept = prune_edges_connectivity_preserving(G, z_min=1.0, top_k=1)

        # Verify exactly 1 connected component remains.
        dsu = _DSU(set(G.nodes()))
        for u, v in kept:
            dsu.union(u, v)
        assert dsu.num_components() == 1

        # Pass-1 keeps 3 edges (one per source).
        # Pass-2 adds exactly 2 bridges (3 components → 1).
        # Total kept = 3 + 2 = 5 (all edges in graph).
        # The key invariant: we never add MORE than necessary.
        pass1_kept = prune_edges_by_zscore(G, z_min=1.0, top_k=1)
        n_bridges_added = len(kept) - len(pass1_kept)
        n_initial_components = 3  # known from graph structure
        assert n_bridges_added <= n_initial_components - 1

