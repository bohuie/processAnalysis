import pytest
import os
from unittest.mock import patch

# ============================================================
# get_pipeline_summary tests (no pipeline needed, just reads disk)
# ============================================================

def test_get_pipeline_summary_empty(tmp_path):
    """Returns zero counts when output dirs don't exist yet."""
    from process_model.api import get_pipeline_summary
    result = get_pipeline_summary(output_root=str(tmp_path))
    assert result["total_graphs"] == 0
    for dataset in ["branching", "pr", "communication"]:
        assert result["by_dataset"][dataset]["graph_count"] == 0

def test_get_pipeline_summary_counts_pngs(tmp_path):
    """Counts PNGs correctly across datasets."""
    from process_model.api import get_pipeline_summary
    pr_dir = tmp_path / "pr" / "some_team"
    pr_dir.mkdir(parents=True)
    (pr_dir / "team1_avg_session.png").write_bytes(b"")
    (pr_dir / "team1_overall.png").write_bytes(b"")

    result = get_pipeline_summary(output_root=str(tmp_path))
    assert result["total_graphs"] == 2
    assert result["by_dataset"]["pr"]["graph_count"] == 2
    assert result["by_dataset"]["branching"]["graph_count"] == 0

# ============================================================
# get_cluster_stats tests (no pipeline needed, just reads CSVs)
# ============================================================

def test_get_cluster_stats_missing_files(tmp_path):
    """Returns None per dataset when cluster CSVs don't exist."""
    from process_model.api import get_cluster_stats
    result = get_cluster_stats(output_root=str(tmp_path))
    for dataset in ["branching", "pr", "communication"]:
        assert result[dataset] is None

def test_get_cluster_stats_reads_csv(tmp_path):
    """Parses cluster CSV correctly."""
    import pandas as pd
    from process_model.api import get_cluster_stats

    pr_dir = tmp_path / "pr"
    pr_dir.mkdir()
    df = pd.DataFrame({
        "team_number": ["1", "2", "3"],
        "cluster_id": [0, 0, 1],
        "k_used": [2, 2, 2],
        "silhouette": [0.45, 0.45, 0.45],
    })
    df.to_csv(pr_dir / "behavior_clusters_pr.csv", index=False)

    result = get_cluster_stats(output_root=str(tmp_path))
    assert result["pr"]["team_count"] == 3
    assert result["pr"]["cluster_count"] == 2
    assert result["pr"]["k_used"] == 2
    assert result["pr"]["silhouette"] == pytest.approx(0.45)

# ============================================================
# run_full_pipeline / run_process_model_only (integration, opt-in)
# ============================================================

def test_run_full_pipeline_skipped_without_data():
    """Pipeline runs without crashing even if input data is missing."""
    if not os.getenv("RUN_INTEGRATION_TEST"):
        pytest.skip("Set RUN_INTEGRATION_TEST=1 to run pipeline integration tests")
    from process_model.api import run_full_pipeline
    result = run_full_pipeline()
    assert "total_graphs" in result

def test_run_process_model_only_skipped_without_data():
    """Process model only run doesn't crash without prior extraction."""
    if not os.getenv("RUN_INTEGRATION_TEST"):
        pytest.skip("Set RUN_INTEGRATION_TEST=1 to run pipeline integration tests")
    from process_model.api import run_process_model_only
    result = run_process_model_only()
    assert "total_graphs" in result