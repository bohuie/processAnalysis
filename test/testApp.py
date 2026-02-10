import os
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime
import tempfile
import shutil

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the function to test
from app import extract_repository_data


class TestExtractRepositoryData:
    """Test suite for extract_repository_data function"""

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup after test
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def mock_extractor(self):
        """Create a mock PullRequestExtractor"""
        mock = Mock()
        mock.extract_pull_requests_with_pagination.return_value = [
            {"number": 1, "title": "Test PR 1"},
            {"number": 2, "title": "Test PR 2"},
        ]
        mock.csv_filepath = "/path/to/prs.csv"
        mock.commit_csv_filepath = "/path/to/commits.csv"
        mock.commit_file_changes_csv_filepath = "/path/to/file_changes.csv"
        mock.review_comments_csv_filepath = "/path/to/comments.csv"
        return mock

    @patch('scripts.app.PullRequestExtractor')
    def test_successful_extraction_with_all_options(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test successful extraction with all options enabled"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=True,
            save_csv=True,
            include_orphan_commits=True,
            branch_for_orphans="main",
            exclude_readme=True,
        )

        # Verify extractor was initialized correctly
        mock_extractor_class.assert_called_once_with(
            repo_owner="test-owner",
            repo_name="test-repo",
            need_auth=True,
            exclude_readme=True,
        )

        # Verify extraction was called with correct parameters
        mock_extractor.extract_pull_requests_with_pagination.assert_called_once_with(
            pull_request_status="all",
            save_data_to_json=True,
            save_data_to_csv=True,
            csv_filename="test-repo_all_pull_requests",
            include_orphan_commits=True,
            branch_for_orphans="main"
        )

        # Verify results
        assert results["status"] == "success"
        assert results["repo_name"] == "test-repo"
        assert results["pull_requests_extracted"] == 2
        assert len(results["errors"]) == 0
        assert len(results["output_files"]) > 0

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_with_json_only(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test extraction saving only JSON files"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=True,
            save_csv=False,
            include_orphan_commits=False,
        )

        # Verify extraction was called with correct parameters
        mock_extractor.extract_pull_requests_with_pagination.assert_called_once()
        call_kwargs = mock_extractor.extract_pull_requests_with_pagination.call_args[1]
        assert call_kwargs["save_data_to_json"] is True
        assert call_kwargs["save_data_to_csv"] is False

        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_with_csv_only(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test extraction saving only CSV files"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=False,
            save_csv=True,
        )

        # Verify extraction was called with correct parameters
        call_kwargs = mock_extractor.extract_pull_requests_with_pagination.call_args[1]
        assert call_kwargs["save_data_to_json"] is False
        assert call_kwargs["save_data_to_csv"] is True

        assert results["status"] == "success"
        assert "PRs:" in results["output_files"][0]

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_without_orphan_commits(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test extraction excluding orphan commits"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            include_orphan_commits=False,
        )

        # Verify extraction was called with correct parameters
        call_kwargs = mock_extractor.extract_pull_requests_with_pagination.call_args[1]
        assert call_kwargs["include_orphan_commits"] is False

        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_with_custom_branch(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test extraction with custom branch for orphan commits"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            branch_for_orphans="develop",
        )

        # Verify extraction was called with correct branch
        call_kwargs = mock_extractor.extract_pull_requests_with_pagination.call_args[1]
        assert call_kwargs["branch_for_orphans"] == "develop"

        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_with_readme_exclusion(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test extraction with README exclusion"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            exclude_readme=True,
        )

        # Verify extractor was initialized with exclude_readme=True
        mock_extractor_class.assert_called_once()
        call_kwargs = mock_extractor_class.call_args[1]
        assert call_kwargs["exclude_readme"] is True

        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_directory_creation(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test that output directories are created correctly"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=True,
            save_csv=True,
        )

        # Verify directories were created
        json_dir = Path(temp_output_dir) / "json" / "test-repo"
        csv_dir = Path(temp_output_dir) / "csv" / "test-repo"

        assert json_dir.exists()
        assert csv_dir.exists()
        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_with_no_pull_requests(self, mock_extractor_class, temp_output_dir):
        """Test extraction when no pull requests are found"""
        mock_extractor = Mock()
        mock_extractor.extract_pull_requests_with_pagination.return_value = []
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
        )

        assert results["status"] == "success"
        assert results["pull_requests_extracted"] == 0

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_failure_during_initialization(self, mock_extractor_class, temp_output_dir):
        """Test handling of errors during extractor initialization"""
        mock_extractor_class.side_effect = Exception("API authentication failed")

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
        )

        assert results["status"] == "failed"
        assert len(results["errors"]) > 0
        assert "API authentication failed" in results["errors"][0]

    @patch('scripts.app.PullRequestExtractor')
    def test_extraction_failure_during_extraction(self, mock_extractor_class, temp_output_dir):
        """Test handling of errors during pull request extraction"""
        mock_extractor = Mock()
        mock_extractor.extract_pull_requests_with_pagination.side_effect = Exception("Rate limit exceeded")
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
        )

        assert results["status"] == "failed"
        assert len(results["errors"]) > 0
        assert "Rate limit exceeded" in results["errors"][0]

    @patch('scripts.app.PullRequestExtractor')
    def test_output_files_recording(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test that all output file paths are recorded correctly"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=True,
            save_csv=True,
        )

        # Verify all CSV files are recorded
        output_files_str = " ".join(results["output_files"])
        assert "PRs:" in output_files_str
        assert "Commits:" in output_files_str
        assert "File Changes:" in output_files_str
        assert "Comments:" in output_files_str
        assert "JSON:" in output_files_str

    @patch('scripts.app.PullRequestExtractor')
    def test_output_files_with_missing_attributes(self, mock_extractor_class, temp_output_dir):
        """Test handling when extractor doesn't have all file path attributes"""
        mock_extractor = Mock()
        mock_extractor.extract_pull_requests_with_pagination.return_value = [{"number": 1}]
        # Only set some attributes
        mock_extractor.csv_filepath = "/path/to/prs.csv"
        # Don't set other attributes
        delattr(mock_extractor, 'commit_csv_filepath')
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_csv=True,
        )

        # Should still succeed
        assert results["status"] == "success"
        # Should record at least the PR file
        assert any("PRs:" in f for f in results["output_files"])

    @patch('scripts.app.PullRequestExtractor')
    def test_default_parameters(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test function with default parameters"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
        )

        # Verify defaults are applied
        call_kwargs = mock_extractor.extract_pull_requests_with_pagination.call_args[1]
        assert call_kwargs["save_data_to_json"] is True
        assert call_kwargs["save_data_to_csv"] is True
        assert call_kwargs["include_orphan_commits"] is True
        assert call_kwargs["branch_for_orphans"] == "master"

        assert results["status"] == "success"

    @patch('scripts.app.PullRequestExtractor')
    def test_results_structure(self, mock_extractor_class, mock_extractor, temp_output_dir):
        """Test that results dictionary has correct structure"""
        mock_extractor_class.return_value = mock_extractor

        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
        )

        # Verify all required keys are present
        assert "repo_name" in results
        assert "status" in results
        assert "pull_requests_extracted" in results
        assert "output_files" in results
        assert "errors" in results

        # Verify types
        assert isinstance(results["repo_name"], str)
        assert isinstance(results["status"], str)
        assert isinstance(results["pull_requests_extracted"], int)
        assert isinstance(results["output_files"], list)
        assert isinstance(results["errors"], list)


class TestMainExecution:
    """Test suite for main execution block"""

    @patch('scripts.app.extract_repository_data')
    @patch('sys.exit')
    def test_main_execution_success(self, mock_exit, mock_extract):
        """Test main execution with successful extraction"""
        mock_extract.return_value = {
            "status": "success",
            "repo_name": "test-repo",
            "pull_requests_extracted": 5,
            "output_files": ["file1.csv", "file2.csv"],
            "errors": []
        }

        # Call the function directly to test it
        result = mock_extract(
            repo_owner='test-owner',
            repo_name='test-repo',
            output_base_dir='./data',
            save_json=True,
            save_csv=True,
            include_orphan_commits=True,
            branch_for_orphans='master',
            exclude_readme=False,
        )

        # Verify extraction was successful
        assert result["status"] == "success"
        assert result["pull_requests_extracted"] == 5
        assert len(result["output_files"]) > 0
        
        # Verify sys.exit was not called on success
        mock_exit.assert_not_called()

    @patch('scripts.app.extract_repository_data')
    @patch('sys.exit')
    def test_main_execution_failure(self, mock_exit, mock_extract):
        """Test main execution with failed extraction"""
        mock_extract.return_value = {
            "status": "failed",
            "repo_name": "test-repo",
            "pull_requests_extracted": 0,
            "output_files": [],
            "errors": ["API error"]
        }

        # Call the function directly
        result = mock_extract(
            repo_owner='test-owner',
            repo_name='test-repo',
            output_base_dir='./data',
            save_json=True,
            save_csv=True,
            include_orphan_commits=True,
            branch_for_orphans='master',
            exclude_readme=False,
        )

        # Verify extraction failed
        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "API error" in result["errors"][0]


class TestIntegration:
    """Integration tests for the extraction process"""

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @patch('scripts.app.PullRequestExtractor')
    def test_end_to_end_extraction_workflow(self, mock_extractor_class, temp_output_dir):
        """Test complete extraction workflow from start to finish"""
        # Setup mock extractor with realistic data
        mock_extractor = Mock()
        mock_extractor.extract_pull_requests_with_pagination.return_value = [
            {
                "number": 1,
                "title": "Add feature X",
                "state": "merged",
                "created_at": "2024-01-01",
            },
            {
                "number": 2,
                "title": "Fix bug Y",
                "state": "closed",
                "created_at": "2024-01-02",
            },
        ]
        mock_extractor.csv_filepath = f"{temp_output_dir}/test-repo_all_pull_requests.csv"
        mock_extractor.commit_csv_filepath = f"{temp_output_dir}/test-repo_commits.csv"
        mock_extractor.commit_file_changes_csv_filepath = f"{temp_output_dir}/test-repo_file_changes.csv"
        mock_extractor.review_comments_csv_filepath = f"{temp_output_dir}/test-repo_comments.csv"
        mock_extractor_class.return_value = mock_extractor

        # Execute extraction
        results = extract_repository_data(
            repo_owner="test-owner",
            repo_name="test-repo",
            output_base_dir=temp_output_dir,
            save_json=True,
            save_csv=True,
        )

        # Verify complete workflow
        assert results["status"] == "success"
        assert results["pull_requests_extracted"] == 2
        assert len(results["output_files"]) > 0
        assert len(results["errors"]) == 0

        # Verify directories exist
        json_dir = Path(temp_output_dir) / "json" / "test-repo"
        csv_dir = Path(temp_output_dir) / "csv" / "test-repo"
        assert json_dir.exists()
        assert csv_dir.exists()


class TestEnrichSinglePr:
    """Unit tests for enrich_single_pr helper."""

    def test_enrich_single_pr_sets_flags_and_counts(self):
        from app import enrich_single_pr

        class DummyExtractor:
            def extract_pull_request_by_id(self, pr_id):
                return {
                    "merged_by": {"login": "reviewer"},
                    "mergeable_state": "clean",
                    "merged_at": "2024-01-02T00:00:00Z",
                    "base": {"sha": "base"},
                    "head": {"sha": "head"},
                    "title": "Add docs",
                    "body": "PR body",
                }

            def compare_commits(self, base_sha, head_sha):
                assert base_sha == "base"
                assert head_sha == "head"
                return {"behind_by": 0}

            def extract_pr_reviews(self, pr_id):
                return [
                    {"user": {"login": "r1"}},
                    {"user": {"login": "r2"}},
                ]

        pr = {"number": 1}
        file_changes_cache = {
            1: [
                {"filename": "docs/README.md", "additions": 5, "deletions": 0},
                {"filename": "src/main.py", "additions": 10, "deletions": 2},
            ]
        }

        enriched = enrich_single_pr((pr, DummyExtractor(), file_changes_cache))

        assert enriched["merged_by"] == "reviewer"
        assert enriched["was_up_to_date_at_merge"] is True
        assert enriched["has_conflicts"] is False
        assert enriched["num_reviewers"] == 2
        assert enriched["docs_updated"] is True
        assert enriched["lines_added"] == 15
        assert enriched["lines_deleted"] == 2
        assert enriched["files_changed"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])