from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load_clustering_module():
    repo_root = Path(__file__).resolve().parents[1]

    path = repo_root / "process_model" / "clustering.py"

    if path.exists():
        spec = importlib.util.spec_from_file_location("clustering_under_test", path)
        assert spec and spec.loader, f"Failed to load spec for {path}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return mod

    raise FileNotFoundError(
        "Could not locate clustering.py. Add its path to CANDIDATE_PATHS in the test."
    )


@pytest.fixture()
def clustering_mod():
    return _load_clustering_module()


def _write_input_csv(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        [
            {"team_number": 1, "from": "START", "to": "A", "count": 0.9, "z_score": 2.0},
            {"team_number": 1, "from": "A", "to": "END", "count": 0.1, "z_score": 0.5},
            {"team_number": 2, "from": "START", "to": "A", "count": 0.7, "z_score": -2.2},
            {"team_number": 2, "from": "A", "to": "END", "count": 0.3, "z_score": -1.7},
            {"team_number": 3, "from": "START", "to": "A", "count": 0.6, "z_score": 0.1},
            {"team_number": 3, "from": "A", "to": "END", "count": 0.4, "z_score": 0.2},
        ]
    )

    fp = tmp_path / "team_transition_edges_avg_session_zscores.csv"
    df.to_csv(fp, index=False)
    return fp


def test_filtered_edges_csv_export(tmp_path: Path, clustering_mod, monkeypatch):
    in_fp = _write_input_csv(tmp_path)

    out_clusters = tmp_path / "behavior_clusters_test.csv"
    out_matrix = tmp_path / "team_transition_matrix_test.csv"
    out_edges = tmp_path / "team_transition_edges_avg_session_zfiltered_test.csv"

    monkeypatch.setattr(clustering_mod, "IN_FP", str(in_fp))
    monkeypatch.setattr(clustering_mod, "OUT_FP", str(out_clusters))
    monkeypatch.setattr(clustering_mod, "MATRIX_OUT_FP", str(out_matrix))
    monkeypatch.setattr(clustering_mod, "FILTERED_EDGES_OUT_FP", str(out_edges))
    monkeypatch.setattr(clustering_mod, "Z_THRESHOLD", 1.645)

    clustering_mod.main()

    # ---- filtered edges export exists
    assert out_edges.exists(), "Filtered edges CSV was not created"

    edges = pd.read_csv(out_edges)

    # required columns
    assert {"team_number", "from", "to", "count", "z_score"}.issubset(edges.columns)

    # both tails condition holds
    assert (edges["z_score"].abs() >= clustering_mod.Z_THRESHOLD).all()

    # dropped team 3 should not be present
    assert set(edges["team_number"].astype(str).unique()) == {"1", "2"}

    # sanity: should only include the 3 surviving edges
    # (team1 START->A; team2 START->A; team2 A->END)
    assert len(edges) == 3
