from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
from test.test_clustering_filtered_edges_export import clustering_mod
import pytest


def _write_input_csv(tmp_path: Path) -> Path:
    # includes both tails + one team that will be dropped
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


def test_transition_matrix_csv_export(tmp_path: Path, clustering_mod, monkeypatch):
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

    # ---- matrix export exists
    assert out_matrix.exists(), "Transition matrix CSV was not created"

    mat = pd.read_csv(out_matrix)
    assert "team_number" in mat.columns, "Matrix CSV should include team_number column"

    # dropped team 3 should not be present
    assert set(mat["team_number"].astype(str).tolist()) == {"1", "2"}

    # columns from FULL df pairs should exist
    assert "START->A" in mat.columns
    assert "A->END" in mat.columns

    # values match surviving edges; filtered-out edges remain 0
    mat = mat.set_index("team_number")
    assert pytest.approx(mat.loc[1, "START->A"], rel=1e-9) == 0.9
    assert pytest.approx(mat.loc[1, "A->END"], rel=1e-9) == 0.0  # filtered out
    assert pytest.approx(mat.loc[2, "START->A"], rel=1e-9) == 0.7
    assert pytest.approx(mat.loc[2, "A->END"], rel=1e-9) == 0.3