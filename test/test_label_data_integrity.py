"""
Test suite for verifying data integrity in label CSV files.

This module tests that:
1. All data from raw CSV files is properly transferred to label CSV
2. Data accuracy (PR IDs, authors, timestamps, etc.)
3. All expected label types are present
4. No data loss or corruption
"""

import os
import sys
import pytest
import pandas as pd
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestLabelDataIntegrity:
    """Test suite for verifying label CSV data integrity"""

    @pytest.fixture
    def team_name(self):
        """Team name for testing"""
        return "year-long-project-team-15"

    @pytest.fixture
    def raw_data_dir(self, team_name):
        """Path to raw CSV data directory"""
        return Path("data/csv") / team_name

    @pytest.fixture
    def labels_dir(self):
        """Path to labels directory"""
        return Path("data/graph_labels")

    @pytest.fixture
    def labels_file(self, team_name, labels_dir):
        """Path to labels CSV file"""
        return labels_dir / f"{team_name}_labels_branching_and_structure.csv"

    @pytest.fixture
    def prs_df(self, raw_data_dir, team_name):
        """Load pull requests CSV"""
        prs_file = next(
            (f for f in raw_data_dir.glob("*.csv") 
             if f.name.endswith("_pull_requests.csv") or f.name.endswith("_all_pull_requests.csv")),
            None
        )
        if prs_file and prs_file.exists():
            return pd.read_csv(prs_file)
        pytest.skip(f"PRs file not found for {team_name}")

    @pytest.fixture
    def commits_df(self, raw_data_dir, team_name):
        """Load commits CSV"""
        commits_file = next(
            (f for f in raw_data_dir.glob("*.csv") 
             if f.name.endswith("_commits.csv") or f.name.endswith("_PR_commits.csv")),
            None
        )
        if commits_file and commits_file.exists():
            return pd.read_csv(commits_file)
        pytest.skip(f"Commits file not found for {team_name}")

    @pytest.fixture
    def file_changes_df(self, raw_data_dir, team_name):
        """Load file changes CSV"""
        file_changes_file = next(
            (f for f in raw_data_dir.glob("*.csv") 
             if f.name.endswith("_file_changes.csv") or f.name.endswith("_commit_file_changes.csv")),
            None
        )
        if file_changes_file and file_changes_file.exists():
            return pd.read_csv(file_changes_file)
        pytest.skip(f"File changes file not found for {team_name}")

    @pytest.fixture
    def labels_df(self, labels_file):
        """Load labels CSV"""
        if not labels_file.exists():
            pytest.skip(f"Labels file not found: {labels_file}")
        return pd.read_csv(labels_file)

    def test_labels_file_exists(self, labels_file):
        """Test that labels file exists"""
        assert labels_file.exists(), f"Labels file should exist: {labels_file}"

    def test_all_prs_have_labels(self, prs_df, labels_df):
        """Test that every PR from raw data has at least one label (excluding bots)"""
        # Filter out bot PRs (same logic as in code_structure_and_branching.py)
        bot_patterns_regex = [
            r'\[bot\]$',
            r'^bot[-_]',
            r'[-_]bot',
            r'^bot\d',
            r'dependabot',
            r'github-actions',
            r'renovate',
            r'greenkeeper',
            r'codecov',
            r'snyk-bot',
            r'github-classroom',
        ]
        
        # Handle both 'author' and 'pr_author' column names
        author_col = "pr_author" if "pr_author" in prs_df.columns else "author"
        
        # Filter bot PRs
        non_bot_prs = prs_df[
            ~prs_df[author_col].str.lower().str.contains(
                '|'.join(bot_patterns_regex), 
                na=False, 
                regex=True
            )
        ]
        
        # Get unique PR IDs from non-bot raw data
        raw_pr_ids = set(non_bot_prs['pr_id'].dropna().unique())
        
        # Get unique PR IDs from labels
        label_pr_ids = set(labels_df['pr_id'].dropna().unique())
        
        # Every non-bot PR should have at least one label
        missing_prs = raw_pr_ids - label_pr_ids
        assert len(missing_prs) == 0, f"PRs missing from labels: {missing_prs}"

    def test_pr_author_consistency(self, prs_df, labels_df):
        """Test that pr_author values match between raw data and labels"""
        # Handle both 'author' and 'pr_author' column names in raw data
        author_col = "pr_author" if "pr_author" in prs_df.columns else "author"
        
        # Create mapping of pr_id -> pr_author from raw data
        raw_pr_authors = dict(zip(prs_df['pr_id'], prs_df[author_col]))
        
        # Check that labels match
        for _, label_row in labels_df.iterrows():
            pr_id = label_row['pr_id']
            label_author = label_row['pr_author']
            
            if pd.notna(pr_id) and pr_id in raw_pr_authors:
                raw_author = raw_pr_authors[pr_id]
                assert label_author == raw_author, \
                    f"PR {pr_id}: author mismatch - raw: {raw_author}, label: {label_author}"

    def test_created_at_consistency(self, prs_df, labels_df):
        """Test that created_at timestamps match between raw data and labels"""
        # Create mapping of pr_id -> created_at from raw data
        raw_pr_timestamps = dict(zip(prs_df['pr_id'], prs_df['created_at']))
        
        # Check that labels match (allowing for timezone format differences)
        for _, label_row in labels_df.iterrows():
            pr_id = label_row['pr_id']
            label_timestamp = label_row['created_at']
            
            if pd.notna(pr_id) and pr_id in raw_pr_timestamps:
                raw_timestamp = raw_pr_timestamps[pr_id]
                # Normalize both to compare (remove timezone info for comparison)
                raw_normalized = str(raw_timestamp).replace('+00:00', 'Z').replace(' ', 'T')
                label_normalized = str(label_timestamp).replace('+00:00', 'Z').replace(' ', 'T')
                
                # Compare date and time parts (ignore timezone format differences)
                assert raw_normalized[:19] == label_normalized[:19], \
                    f"PR {pr_id}: timestamp mismatch - raw: {raw_timestamp}, label: {label_timestamp}"

    def test_all_expected_label_types_present(self, labels_df, prs_df):
        """Test that all expected main_label types are present"""
        # Core labels that should always be present
        required_labels = {
            "Branch Name",
            "Features Per Branch",
            "Feature Size",
            "Refactor Size",
            "PR Status",
            "Merge State"
        }
        
        # Repository Status is optional (only if was_up_to_date_at_merge column exists)
        optional_labels = {
            "Repository Status"
        }
        
        actual_labels = set(labels_df['main_label'].dropna().unique())
        
        # Check required labels
        missing_required = required_labels - actual_labels
        assert len(missing_required) == 0, \
            f"Missing required label types: {missing_required}"
        
        # Repository Status is optional - only check if column exists in raw data
        if "was_up_to_date_at_merge" in prs_df.columns:
            missing_optional = optional_labels - actual_labels
            if len(missing_optional) > 0:
                # This is a warning, not a failure, since the column might exist but have no valid data
                print(f"Warning: Optional label type not present: {missing_optional}")

    def test_branch_name_labels_present(self, labels_df):
        """Test that branch name labels exist for PRs with branches"""
        branch_labels = labels_df[labels_df['main_label'] == 'Branch Name']
        assert len(branch_labels) > 0, "Should have at least some branch name labels"
        
        # Check that branch names are present where expected
        branch_labels_with_name = branch_labels[branch_labels['branch_name'].notna()]
        assert len(branch_labels_with_name) > 0, "Should have branch names in branch labels"

    def test_features_per_branch_labels_present(self, labels_df):
        """Test that features per branch labels exist"""
        features_labels = labels_df[labels_df['main_label'] == 'Features Per Branch']
        assert len(features_labels) > 0, "Should have features per branch labels"
        
        # Check that events are either "one" or "multiple"
        events = features_labels['event'].unique()
        assert any('one' in str(e).lower() for e in events), "Should have 'one Features Per Branch' events"
        assert any('multiple' in str(e).lower() for e in events) or len(events) == 1, \
            "Should have 'multiple Features Per Branch' events or only one type"

    def test_feature_size_labels_present(self, labels_df):
        """Test that feature size labels exist"""
        feature_size_labels = labels_df[labels_df['main_label'] == 'Feature Size']
        assert len(feature_size_labels) > 0, "Should have feature size labels"
        
        # Check that commit_sha is present for feature size labels
        feature_size_with_sha = feature_size_labels[feature_size_labels['commit_sha'].notna()]
        assert len(feature_size_with_sha) > 0, "Feature size labels should have commit_sha"

    def test_refactor_size_labels_present(self, labels_df):
        """Test that refactor size labels exist"""
        refactor_labels = labels_df[labels_df['main_label'] == 'Refactor Size']
        assert len(refactor_labels) > 0, "Should have refactor size labels"
        
        # Check that filename is present for refactor labels
        refactor_with_filename = refactor_labels[refactor_labels['filename'].notna()]
        assert len(refactor_with_filename) > 0, "Refactor size labels should have filename"

    def test_pr_status_labels_present(self, labels_df):
        """Test that PR status labels exist"""
        pr_status_labels = labels_df[labels_df['main_label'] == 'PR Status']
        assert len(pr_status_labels) > 0, "Should have PR status labels"
        
        # Check that events are valid
        events = pr_status_labels['event'].unique()
        valid_events = {'closed', 'still_open', 'merged'}
        assert all(e in valid_events for e in events), \
            f"PR status events should be in {valid_events}, got: {set(events)}"

    def test_merge_state_labels_present(self, labels_df):
        """Test that merge state labels exist"""
        merge_labels = labels_df[labels_df['main_label'] == 'Merge State']
        assert len(merge_labels) > 0, "Should have merge state labels"
        
        # Check that events are valid
        events = merge_labels['event'].unique()
        valid_events = {'no_merge', 'self_merge', 'reviewed_merge'}
        assert all(e in valid_events for e in events), \
            f"Merge state events should be in {valid_events}, got: {set(events)}"

    def test_commit_sha_consistency(self, commits_df, labels_df):
        """Test that commit SHAs in labels match those in raw commits data"""
        # Get all unique commit SHAs from raw data
        raw_commit_shas = set(commits_df['commit_sha'].dropna().unique())
        
        # Get commit SHAs from labels (Feature Size and Refactor Size)
        label_commit_shas = set(
            labels_df[labels_df['commit_sha'].notna()]['commit_sha'].unique()
        )
        
        # All commit SHAs in labels should exist in raw data
        unknown_shas = label_commit_shas - raw_commit_shas
        assert len(unknown_shas) == 0, \
            f"Commit SHAs in labels not found in raw data: {list(unknown_shas)[:10]}"

    def test_file_path_consistency(self, file_changes_df, labels_df):
        """Test that file paths in refactor labels match those in raw file changes"""
        # Get all unique file paths from raw data
        raw_file_paths = set(file_changes_df['file_path'].dropna().unique())
        
        # Get file paths from labels (Refactor Size uses 'filename' column)
        refactor_labels = labels_df[labels_df['main_label'] == 'Refactor Size']
        label_file_paths = set(refactor_labels['filename'].dropna().unique())
        
        # All file paths in labels should exist in raw data
        unknown_paths = label_file_paths - raw_file_paths
        assert len(unknown_paths) == 0, \
            f"File paths in labels not found in raw data: {list(unknown_paths)[:10]}"

    def test_no_duplicate_events(self, labels_df):
        """Test that there are no duplicate events for the same PR and label type"""
        # Group by pr_id, main_label, and event
        duplicates = labels_df.groupby(['pr_id', 'main_label', 'event']).size()
        duplicates = duplicates[duplicates > 1]
        
        # Some duplicates are expected (e.g., multiple refactor size events for different files)
        # But we should check that they make sense
        if len(duplicates) > 0:
            # For Refactor Size, duplicates are expected (one per file)
            # For Feature Size, duplicates might be expected (one per commit)
            # But for Branch Name, PR Status, Merge State, there should typically be one per PR
            single_event_labels = ['Branch Name', 'PR Status', 'Merge State', 'Features Per Branch']
            for (pr_id, main_label, event), count in duplicates.items():
                if main_label in single_event_labels:
                    assert count == 1, \
                        f"PR {pr_id} has {count} duplicate {main_label} events with event '{event}'"

    def test_required_columns_present(self, labels_df):
        """Test that all required columns are present in labels CSV"""
        required_columns = [
            'pr_id',
            'pr_author',
            'created_at',
            'event',
            'main_label',
            'llm_output',
            'llm_timestamp'
        ]
        
        missing_columns = set(required_columns) - set(labels_df.columns)
        assert len(missing_columns) == 0, \
            f"Missing required columns: {missing_columns}"

    def test_no_null_pr_ids(self, labels_df):
        """Test that there are no null PR IDs"""
        null_pr_ids = labels_df[labels_df['pr_id'].isna()]
        assert len(null_pr_ids) == 0, \
            f"Found {len(null_pr_ids)} rows with null pr_id"

    def test_no_null_main_labels(self, labels_df):
        """Test that there are no null main labels"""
        null_labels = labels_df[labels_df['main_label'].isna()]
        assert len(null_labels) == 0, \
            f"Found {len(null_labels)} rows with null main_label"

    def test_no_null_events(self, labels_df):
        """Test that there are no null events"""
        null_events = labels_df[labels_df['event'].isna()]
        assert len(null_events) == 0, \
            f"Found {len(null_events)} rows with null event"

    def test_llm_timestamp_format(self, labels_df):
        """Test that llm_timestamp is in correct format"""
        # Check that llm_timestamp exists and is not null
        null_timestamps = labels_df[labels_df['llm_timestamp'].isna()]
        assert len(null_timestamps) == 0, \
            f"Found {len(null_timestamps)} rows with null llm_timestamp"
        
        # Check format (should be ISO format with Z)
        sample_timestamp = labels_df['llm_timestamp'].iloc[0]
        assert 'T' in str(sample_timestamp), \
            f"llm_timestamp should be in ISO format, got: {sample_timestamp}"

    def test_merged_at_present_for_merge_events(self, labels_df):
        """Test that merged_at is present for merge state events"""
        merge_labels = labels_df[labels_df['main_label'] == 'Merge State']
        merged_events = merge_labels[merge_labels['event'].isin(['self_merge', 'reviewed_merge'])]
        
        # Merged events should have merged_at timestamp
        merged_without_timestamp = merged_events[merged_events['merged_at'].isna()]
        assert len(merged_without_timestamp) == 0, \
            f"Found {len(merged_without_timestamp)} merged events without merged_at timestamp"

    def test_label_counts_reasonable(self, prs_df, labels_df):
        """Test that label counts are reasonable (not too few)"""
        # Filter out bot PRs (same logic as in code_structure_and_branching.py)
        bot_patterns_regex = [
            r'\[bot\]$',
            r'^bot[-_]',
            r'[-_]bot',
            r'^bot\d',
            r'dependabot',
            r'github-actions',
            r'renovate',
            r'greenkeeper',
            r'codecov',
            r'snyk-bot',
            r'github-classroom',
        ]
        
        author_col = "pr_author" if "pr_author" in prs_df.columns else "author"
        non_bot_prs = prs_df[
            ~prs_df[author_col].str.lower().str.contains(
                '|'.join(bot_patterns_regex), 
                na=False, 
                regex=True
            )
        ]
        
        num_prs = len(non_bot_prs)
        num_labels = len(labels_df)
        
        # Each PR should have multiple labels (at least 4 labels per PR)
        # Branch Name, Features Per Branch, PR Status, Merge State are always present
        # Plus Feature Size and Refactor Size for commits (can be many per PR)
        min_labels_per_pr = 4
        
        avg_labels_per_pr = num_labels / num_prs if num_prs > 0 else 0
        
        assert avg_labels_per_pr >= min_labels_per_pr, \
            f"Too few labels per PR: {avg_labels_per_pr:.2f} (expected at least {min_labels_per_pr})"
        
        # Check that each PR has at least the core labels
        core_labels_per_pr = labels_df.groupby('pr_id')['main_label'].apply(
            lambda x: len(set(x))
        )
        min_core_labels = 4  # Branch Name, Features Per Branch, PR Status, Merge State
        prs_with_few_labels = core_labels_per_pr[core_labels_per_pr < min_core_labels]
        assert len(prs_with_few_labels) == 0, \
            f"PRs with too few core label types: {prs_with_few_labels.to_dict()}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

