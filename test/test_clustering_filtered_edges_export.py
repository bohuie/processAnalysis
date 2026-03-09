from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

@pytest.fixture()
def clustering_mod():
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


def test_filtered_edges_csv_export(tmp_path: Path, clustering_mod):
    in_fp = _write_input_csv(tmp_path)

    out_edges = tmp_path / "team_transition_edges_avg_session_zfiltered_test.csv"

    df = pd.read_csv(in_fp)
    teams, _pairs, X, df_filt = clustering_mod.build_team_matrix(df, z_threshold=1.645)
    nonzero_mask = (X.sum(axis=1) > 0)
    kept_teams = [t for t, keep in zip(teams, nonzero_mask) if keep]

    df_filt = df_filt.copy()
    df_filt["team_number"] = df_filt["team_number"].astype(str)
    df_filt_kept = df_filt[df_filt["team_number"].isin(set(map(str, kept_teams)))].copy()

    cols_first = ["team_number", "from", "to", "count", "z_score"]
    remaining = [c for c in df_filt_kept.columns if c not in cols_first]
    df_filt_kept = df_filt_kept[cols_first + remaining]
    df_filt_kept.to_csv(out_edges, index=False)

    # ---- filtered edges export exists
    assert out_edges.exists(), "Filtered edges CSV was not created"

    edges = pd.read_csv(out_edges)

    # required columns
    assert {"team_number", "from", "to", "count", "z_score"}.issubset(edges.columns)

    # both tails condition holds
    assert (edges["z_score"].abs() >= 1.645).all()

    # dropped team 3 should not be present
    assert set(edges["team_number"].astype(str).unique()) == {"1", "2"}

    # sanity: should only include the 3 surviving edges
    # (team1 START->A; team2 START->A; team2 A->END)
    assert len(edges) == 3
