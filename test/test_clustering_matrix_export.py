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


def test_transition_matrix_csv_export(tmp_path: Path, clustering_mod):
    in_fp = _write_input_csv(tmp_path)

    out_matrix = tmp_path / "team_transition_matrix_test.csv"

    df = pd.read_csv(in_fp)
    teams, pairs, X, _df_filt = clustering_mod.build_team_matrix(df, z_threshold=1.645)
    nonzero_mask = (X.sum(axis=1) > 0)
    kept_teams = [t for t, keep in zip(teams, nonzero_mask) if keep]
    X = X[nonzero_mask]

    col_names = [f"{a}->{b}" for (a, b) in pairs]
    matrix_df = pd.DataFrame(X, index=kept_teams, columns=col_names)
    matrix_df.index.name = "team_number"
    matrix_df.to_csv(out_matrix)

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