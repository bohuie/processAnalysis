"""
Test suite for event_labelling.CodeStructure_Branching.code_structure_and_branching module.

This module tests the code structure and branching labeling functionality including:
- Data cleaning and enrichment functions
- Branch name processing
- Anonymization functions
- Label generation functions (with mocked LLM calls)
- Main processing workflow
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from event_labelling.CodeStructure_Branching.code_structure_and_branching import (
    clean_review_comments,
    enrich_prs_and_comments,
    get_unique_branch_names,
    get_branch_pr_mapping,
    load_anonymization_mapping,
    anonymize_column,
    anonymize_branch_names,
    ask_ollama,
    label_features_per_branch,
    assess_branch_meaningfulness,
    label_branch_names,
    label_feature_size,
    label_refactor_size,
    label_repo_status,
    label_pr_status,
    label_merge_state,
    diagnose_timestamp_issues,
)


class TestCleanReviewComments:
    """Test suite for clean_review_comments function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_clean_review_comments_with_dict_author(self, temp_dir):
        """Test cleaning review comments with dict-formatted author field"""
        # Create test CSV file
        test_file = Path(temp_dir) / "test_comments.csv"
        df = pd.DataFrame({
            'pr_id': [1, 2],
            'author': ["{'username': 'user1'}", "user2"],
            'created_at': ['2024-01-15T10:30:00', '2024-01-16T12:00:00']
        })
        df.to_csv(test_file, index=False)

        # Run cleaning
        clean_review_comments(Path(temp_dir))

        # Verify results
        result_df = pd.read_csv(test_file)
        assert result_df['author'].iloc[0] == 'user1'
        assert result_df['author'].iloc[1] == 'user2'

    def test_clean_review_comments_timestamp_formatting(self, temp_dir):
        """Test that timestamps are formatted to UTC Z format"""
        test_file = Path(temp_dir) / "test_comments.csv"
        df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00+05:00']
        })
        df.to_csv(test_file, index=False)

        clean_review_comments(Path(temp_dir))

        result_df = pd.read_csv(test_file)
        assert result_df['created_at'].iloc[0].endswith('Z')

    def test_clean_review_comments_no_file(self, temp_dir):
        """Test handling when no comment files exist"""
        # Should not raise an error
        clean_review_comments(Path(temp_dir))

    def test_clean_review_comments_missing_author_column(self, temp_dir):
        """Test handling when author column is missing"""
        test_file = Path(temp_dir) / "test_comments.csv"
        df = pd.DataFrame({
            'pr_id': [1],
            'comment': ['test']
        })
        df.to_csv(test_file, index=False)

        # Should not raise an error
        clean_review_comments(Path(temp_dir))


class TestEnrichPRsAndComments:
    """Test suite for enrich_prs_and_comments function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    @pytest.fixture
    def sample_data(self, temp_dir):
        """Create sample data files"""
        # PRs CSV
        prs_file = Path(temp_dir) / "test_pull_requests.csv"
        prs_df = pd.DataFrame({
            'pr_id': [1, 2],
            'author': ['user1', 'user2'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z']
        })
        prs_df.to_csv(prs_file, index=False)

        # Commits CSV
        commits_file = Path(temp_dir) / "test_commits.csv"
        commits_df = pd.DataFrame({
            'pr_id': [1, 1, 2],
            'file_path': ['file1.js', 'file2.js', 'file3.js'],
            'lines_added': [10, 20, 15],
            'lines_deleted': [5, 10, 5]
        })
        commits_df.to_csv(commits_file, index=False)

        # Comments CSV
        comments_file = Path(temp_dir) / "test_comments.csv"
        comments_df = pd.DataFrame({
            'pr_id': [1, 1, 2],
            'author': ['user1', 'user2', 'user1'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-15T11:00:00Z', '2024-01-16T12:00:00Z']
        })
        comments_df.to_csv(comments_file, index=False)

        return temp_dir

    def test_enrich_prs_and_comments_adds_top_file(self, sample_data):
        """Test that top file information is added to PRs"""
        enrich_prs_and_comments(Path(sample_data))

        # Read enriched PRs
        prs_file = Path(sample_data) / "test_pull_requests.csv"
        enriched_prs = pd.read_csv(prs_file)

        assert 'top_file' in enriched_prs.columns
        assert 'top_file_change_%' in enriched_prs.columns
        assert 'docs_updated' in enriched_prs.columns

    def test_enrich_prs_and_comments_adds_order_of_review(self, sample_data):
        """Test that order_of_review is added to comments"""
        enrich_prs_and_comments(Path(sample_data))

        # Read enriched comments
        comments_file = Path(sample_data) / "test_comments.csv"
        enriched_comments = pd.read_csv(comments_file)

        assert 'order_of_review' in enriched_comments.columns
        # First comment should be "first"
        assert enriched_comments['order_of_review'].iloc[0] == 'first'


class TestGetUniqueBranchNames:
    """Test suite for get_unique_branch_names function"""

    def test_get_unique_branch_names(self):
        """Test extracting unique branch names"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2, 3],
            'head_branch': ['feature/login', 'feature/login', 'fix/bug'],
            'author': ['user1', 'user2', 'user3']
        })

        branches = get_unique_branch_names(prs_df)

        assert len(branches) == 2
        assert 'feature/login' in branches
        assert 'fix/bug' in branches

    def test_get_unique_branch_names_no_branch_column(self):
        """Test handling when head_branch column is missing"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2],
            'author': ['user1', 'user2']
        })

        branches = get_unique_branch_names(prs_df)

        assert len(branches) == 0

    def test_get_unique_branch_names_with_nulls(self):
        """Test handling null branch names"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2, 3],
            'head_branch': ['feature/login', None, 'fix/bug'],
            'author': ['user1', 'user2', 'user3']
        })

        branches = get_unique_branch_names(prs_df)

        assert len(branches) == 2
        assert None not in branches


class TestGetBranchPRMapping:
    """Test suite for get_branch_pr_mapping function"""

    def test_get_branch_pr_mapping(self):
        """Test creating branch to PR mapping"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2, 3],
            'head_branch': ['feature/login', 'feature/login', 'fix/bug'],
            'author': ['user1', 'user2', 'user3'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z', '2024-01-17T14:00:00Z']
        })

        mapping = get_branch_pr_mapping(prs_df)

        assert 'feature/login' in mapping
        assert 'fix/bug' in mapping
        assert len(mapping['feature/login']) == 2
        assert len(mapping['fix/bug']) == 1

    def test_get_branch_pr_mapping_with_pr_author_column(self):
        """Test mapping with pr_author column"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2],
            'head_branch': ['feature/login', 'fix/bug'],
            'pr_author': ['user1', 'user2'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z']
        })

        mapping = get_branch_pr_mapping(prs_df)

        assert len(mapping) == 2
        assert mapping['feature/login'][0]['pr_author'] == 'user1'


class TestAnonymization:
    """Test suite for anonymization functions"""

    def test_anonymize_column(self):
        """Test anonymizing a column"""
        series = pd.Series(['John Doe', 'Jane Smith', 'John Doe'])
        mapping = {'John Doe': 'Student1', 'Jane Smith': 'Student2'}

        result = anonymize_column(series, mapping)

        assert result.iloc[0] == 'Student1'
        assert result.iloc[1] == 'Student2'
        assert result.iloc[2] == 'Student1'

    def test_anonymize_column_case_insensitive(self):
        """Test anonymization is case-insensitive"""
        series = pd.Series(['john doe', 'JOHN DOE'])
        mapping = {'John Doe': 'Student1'}

        result = anonymize_column(series, mapping)

        assert result.iloc[0] == 'Student1'
        assert result.iloc[1] == 'Student1'

    def test_anonymize_column_empty_mapping(self):
        """Test anonymization with empty mapping"""
        series = pd.Series(['John Doe', 'Jane Smith'])
        mapping = {}

        result = anonymize_column(series, mapping)

        assert list(result) == list(series)

    def test_anonymize_branch_names(self):
        """Test anonymizing branch names"""
        series = pd.Series(['feature/john-doe-login', 'fix/jane-smith-bug'])
        mapping = {'john-doe': 'Student1', 'jane-smith': 'Student2'}

        result = anonymize_branch_names(series, mapping)

        assert 'Student1' in result.iloc[0]
        assert 'Student2' in result.iloc[1]


class TestLabelFeaturesPerBranch:
    """Test suite for label_features_per_branch function"""

    def test_label_features_per_branch_one_feature(self):
        """Test labeling with one feature per branch"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'head_branch': ['feature/login'],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z']
        })

        result_df = label_features_per_branch(prs_df)

        assert len(result_df) == 1
        assert result_df.iloc[0]['event'] == 'one Features Per Branch'
        assert result_df.iloc[0]['main_label'] == 'Features Per Branch'

    def test_label_features_per_branch_multiple_features(self):
        """Test labeling with multiple features per branch"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2, 3],
            'head_branch': ['feature/login', 'feature/login', 'feature/login'],
            'author': ['user1', 'user2', 'user3'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z', '2024-01-17T14:00:00Z']
        })

        result_df = label_features_per_branch(prs_df)

        assert len(result_df) == 3
        assert all(result_df['event'] == 'multiple Features Per Branch')
        assert all(result_df['main_label'] == 'Features Per Branch')


class TestAssessBranchMeaningfulness:
    """Test suite for assess_branch_meaningfulness function"""

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ask_ollama')
    def test_assess_branch_meaningfulness_meaningful(self, mock_ollama):
        """Test assessing meaningful branch name"""
        mock_ollama.return_value = """
        REASON: The branch name clearly indicates this is about user authentication
        PREDICTION: meaningful
        CONFIDENCE: 95
        """

        label, reason, confidence, llm_output = assess_branch_meaningfulness(
            "feature/user-authentication",
            "Add user login",
            "Implements OAuth2"
        )

        assert label == "Meaningful Branch Name"
        assert len(reason) > 0
        assert 0 <= confidence <= 100
        assert mock_ollama.called

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ask_ollama')
    def test_assess_branch_meaningfulness_random(self, mock_ollama):
        """Test assessing random branch name"""
        mock_ollama.return_value = """
        REASON: The branch name is generic and doesn't describe the PR
        PREDICTION: random
        CONFIDENCE: 90
        """

        label, reason, confidence, llm_output = assess_branch_meaningfulness(
            "test",
            "Add new feature",
            "This PR adds a feature"
        )

        assert label == "Random Branch Name"
        assert len(reason) > 0
        assert 0 <= confidence <= 100

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ask_ollama')
    def test_assess_branch_meaningfulness_fallback(self, mock_ollama):
        """Test fallback when LLM output doesn't match expected format"""
        mock_ollama.return_value = "meaningful"

        label, reason, confidence, llm_output = assess_branch_meaningfulness(
            "feature/test",
            "Test",
            "Test"
        )

        assert label == "Meaningful Branch Name"
        assert confidence == 50  # Default confidence


class TestLabelBranchNames:
    """Test suite for label_branch_names function"""

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ask_ollama')
    def test_label_branch_names(self, mock_ollama):
        """Test labeling branch names"""
        mock_ollama.return_value = """
        REASON: The branch name is meaningful
        PREDICTION: meaningful
        CONFIDENCE: 85
        """

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'head_branch': ['feature/login'],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'title': ['Add login feature'],
            'body': ['Implements user authentication']
        })

        labels_df, reasoning_df = label_branch_names(prs_df)

        assert len(labels_df) > 0
        assert len(reasoning_df) > 0
        assert labels_df.iloc[0]['main_label'] == 'Branch Name'

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ask_ollama')
    def test_label_branch_names_main_master_auto_labeled(self, mock_ollama):
        """Test that main/master branches are auto-labeled"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'head_branch': ['main'],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'title': ['Test'],
            'body': ['Test']
        })

        labels_df, reasoning_df = label_branch_names(prs_df)

        # Should not call Ollama for main/master
        assert not mock_ollama.called
        assert len(labels_df) > 0
        assert labels_df.iloc[0]['event'] == 'Random Branch Name'


class TestLabelFeatureSize:
    """Test suite for label_feature_size function"""

    def test_label_feature_size_small(self):
        """Test labeling small feature size"""
        commits_df = pd.DataFrame({
            'commit_sha': ['sha1', 'sha1'],
            'pr_id': [1, 1],
            'file_path': ['file1.js', 'file2.js'],
            'lines_added': [10, 15],
            'lines_deleted': [5, 5]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_feature_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) > 0
        assert result_df.iloc[0]['main_label'] == 'Feature Size'
        assert result_df.iloc[0]['event'] == 'Small Feature Size'

    def test_label_feature_size_large(self):
        """Test labeling large feature size"""
        commits_df = pd.DataFrame({
            'commit_sha': ['sha1', 'sha1'],
            'pr_id': [1, 1],
            'file_path': ['file1.js', 'file2.js'],
            'lines_added': [100, 150],
            'lines_deleted': [10, 10]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_feature_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'Large Feature Size'


class TestLabelRefactorSize:
    """Test suite for label_refactor_size function"""

    def test_label_refactor_size_small(self):
        """Test labeling small refactor size"""
        commits_df = pd.DataFrame({
            'pr_id': [1],
            'commit_sha': ['sha1'],
            'file_path': ['file1.js'],
            'lines_added': [20],
            'lines_deleted': [10]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_refactor_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) > 0
        assert result_df.iloc[0]['main_label'] == 'Refactor Size'
        assert result_df.iloc[0]['event'] == 'Small Refactor Size'
        assert result_df.iloc[0]['filename'] == 'file1.js'

    def test_label_refactor_size_large(self):
        """Test labeling large refactor size"""
        commits_df = pd.DataFrame({
            'pr_id': [1],
            'commit_sha': ['sha1'],
            'file_path': ['file1.js'],
            'lines_added': [100],
            'lines_deleted': [50]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_refactor_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'Large Refactor Size'

    def test_label_refactor_size_no_file_path(self):
        """Test handling when file_path column is missing"""
        commits_df = pd.DataFrame({
            'pr_id': [1],
            'commit_sha': ['sha1'],
            'lines_added': [20],
            'lines_deleted': [10]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_refactor_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) == 0


class TestLabelRepoStatus:
    """Test suite for label_repo_status function"""

    def test_label_repo_status_up_to_date(self):
        """Test labeling up-to-date repository status"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'pr_author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'was_up_to_date_at_merge': [True]
        })

        result_df = label_repo_status(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['main_label'] == 'Repository Status'
        assert result_df.iloc[0]['event'] == 'up-to-date'

    def test_label_repo_status_outdated(self):
        """Test labeling outdated repository status"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'pr_author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'was_up_to_date_at_merge': [False],
            'has_conflicts': [True]
        })

        result_df = label_repo_status(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'outdated'

    def test_label_repo_status_missing_column(self):
        """Test handling when column is missing"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'pr_author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z']
        })

        result_df = label_repo_status(prs_df)

        assert len(result_df) == 0


class TestLabelPRStatus:
    """Test suite for label_pr_status function"""

    def test_label_pr_status_open(self):
        """Test labeling open PR status"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'state': ['open']
        })

        result_df = label_pr_status(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['main_label'] == 'PR Status'
        assert result_df.iloc[0]['event'] == 'still_open'

    def test_label_pr_status_closed(self):
        """Test labeling closed PR status"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'state': ['closed']
        })

        result_df = label_pr_status(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'closed'

    def test_label_pr_status_with_pr_author_column(self):
        """Test with pr_author column instead of author"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'pr_author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'state': ['open']
        })

        result_df = label_pr_status(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['pr_author'] == 'user1'


class TestLabelMergeState:
    """Test suite for label_merge_state function"""

    def test_label_merge_state_no_merge(self):
        """Test labeling PR with no merge"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'merged_at': [None]
        })

        result_df = label_merge_state(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['main_label'] == 'Merge State'
        assert result_df.iloc[0]['event'] == 'no_merge'

    def test_label_merge_state_self_merge(self):
        """Test labeling self-merge"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'merged_at': ['2024-01-16T12:00:00Z'],
            'merged_by': ['user1']
        })

        result_df = label_merge_state(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'self_merge'

    def test_label_merge_state_reviewed_merge(self):
        """Test labeling reviewed merge"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'merged_at': ['2024-01-16T12:00:00Z'],
            'merged_by': ['user2']
        })

        result_df = label_merge_state(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'reviewed_merge'


class TestDiagnoseTimestampIssues:
    """Test suite for diagnose_timestamp_issues function"""

    def test_diagnose_timestamp_issues_no_missing(self):
        """Test diagnosis when no timestamps are missing"""
        df = pd.DataFrame({
            'pr_id': [1, 2],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z'],
            'main_label': ['Branch Name', 'PR Status']
        })

        # Should not raise an error
        diagnose_timestamp_issues(df)

    def test_diagnose_timestamp_issues_with_missing(self):
        """Test diagnosis when timestamps are missing"""
        df = pd.DataFrame({
            'pr_id': [1, 2],
            'pr_author': ['user1', 'user2'],
            'created_at': ['2024-01-15T10:30:00Z', None],
            'main_label': ['Branch Name', 'PR Status'],
            'event': ['Random Branch Name', 'closed']
        })

        # Should not raise an error, just print warnings
        diagnose_timestamp_issues(df)


class TestAskOllama:
    """Test suite for ask_ollama function"""

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ollama.chat')
    def test_ask_ollama_success(self, mock_chat):
        """Test successful Ollama call"""
        mock_chat.return_value = {
            'message': {'content': 'Test response'}
        }

        result = ask_ollama("Test prompt")

        assert result == 'Test response'
        mock_chat.assert_called_once()

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.ollama.chat')
    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.time.sleep')
    def test_ask_ollama_retry_on_error(self, mock_sleep, mock_chat):
        """Test that Ollama retries on error"""
        # First call fails, second succeeds
        mock_chat.side_effect = [
            Exception("Connection error"),
            {'message': {'content': 'Success response'}}
        ]

        result = ask_ollama("Test prompt")

        assert result == 'Success response'
        assert mock_chat.call_count == 2
        assert mock_sleep.called


class TestLoadAnonymizationMapping:
    """Test suite for load_anonymization_mapping function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.os.path.exists')
    @patch('builtins.open', create=True)
    def test_load_anonymization_mapping_success(self, mock_open, mock_exists):
        """Test loading anonymization mapping successfully"""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = '{"John Doe": "Student1"}'
        
        # Mock json.load
        with patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.json.load') as mock_json:
            mock_json.return_value = {"John Doe": "Student1"}
            
            result = load_anonymization_mapping()
            
            assert result == {"John Doe": "Student1"}

    @patch('event_labelling.CodeStructure_Branching.code_structure_and_branching.os.path.exists')
    def test_load_anonymization_mapping_file_not_found(self, mock_exists):
        """Test handling when mapping file doesn't exist"""
        mock_exists.return_value = False

        result = load_anonymization_mapping()

        assert result == {}


class TestEdgeCases:
    """Test suite for edge cases and error handling"""

    def test_label_feature_size_no_commits(self):
        """Test feature size labeling with no commits"""
        commits_df = pd.DataFrame(columns=['commit_sha', 'pr_id', 'file_path', 'lines_added', 'lines_deleted'])
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })
        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_feature_size(commits_df, prs_df, pr_created_at_lookup)

        assert len(result_df) == 0

    def test_label_feature_size_no_net_additions(self):
        """Test feature size labeling when deletions exceed additions"""
        commits_df = pd.DataFrame({
            'commit_sha': ['sha1', 'sha1'],
            'pr_id': [1, 1],
            'file_path': ['file1.js', 'file2.js'],
            'lines_added': [10, 5],
            'lines_deleted': [15, 10]  # More deletions than additions
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_feature_size(commits_df, prs_df, pr_created_at_lookup)

        # Should skip commits with no net additions
        assert len(result_df) == 0

    def test_label_refactor_size_zero_changes(self):
        """Test refactor size labeling with zero changes"""
        commits_df = pd.DataFrame({
            'pr_id': [1],
            'commit_sha': ['sha1'],
            'file_path': ['file1.js'],
            'lines_added': [0],
            'lines_deleted': [0]
        })

        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1']
        })

        pr_created_at_lookup = {1: '2024-01-15T10:30:00Z'}

        result_df = label_refactor_size(commits_df, prs_df, pr_created_at_lookup)

        # Should skip files with zero changes
        assert len(result_df) == 0

    def test_label_repo_status_string_boolean(self):
        """Test repo status labeling with string boolean values"""
        prs_df = pd.DataFrame({
            'pr_id': [1, 2],
            'pr_author': ['user1', 'user2'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z'],
            'was_up_to_date_at_merge': ['True', 'False']
        })

        result_df = label_repo_status(prs_df)

        assert len(result_df) == 2
        assert result_df.iloc[0]['event'] == 'up-to-date'
        assert result_df.iloc[1]['event'] == 'outdated'

    def test_label_merge_state_empty_string_merged_at(self):
        """Test merge state labeling with empty string merged_at"""
        prs_df = pd.DataFrame({
            'pr_id': [1],
            'author': ['user1'],
            'created_at': ['2024-01-15T10:30:00Z'],
            'merged_at': ['']
        })

        result_df = label_merge_state(prs_df)

        assert len(result_df) > 0
        assert result_df.iloc[0]['event'] == 'no_merge'

    def test_get_branch_pr_mapping_empty_dataframe(self):
        """Test branch PR mapping with empty dataframe"""
        prs_df = pd.DataFrame()

        mapping = get_branch_pr_mapping(prs_df)

        assert len(mapping) == 0

    def test_get_unique_branch_names_empty_dataframe(self):
        """Test unique branch names with empty dataframe"""
        prs_df = pd.DataFrame()

        branches = get_unique_branch_names(prs_df)

        assert len(branches) == 0

    def test_anonymize_column_with_nan(self):
        """Test anonymization with NaN values"""
        series = pd.Series(['John Doe', np.nan, 'Jane Smith'])
        mapping = {'John Doe': 'Student1'}

        result = anonymize_column(series, mapping)

        assert result.iloc[0] == 'Student1'
        # NaN values are converted to string 'nan' by astype(str)
        assert str(result.iloc[1]).lower() == 'nan' or pd.isna(result.iloc[1])
        assert result.iloc[2] == 'Jane Smith'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

