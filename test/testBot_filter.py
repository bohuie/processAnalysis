import os
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
import tempfile
import shutil
import pandas as pd

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the functions to test
from enrich_output.bot_filter import (
    normalize_timestamp_to_utc_z,
    is_timestamp_column,
    normalize_timestamps_in_dataframe,
    normalize_timestamps_in_file,
    find_all_teams,
    normalize_timestamps_for_all_teams
)


class TestNormalizeTimestampToUtcZ:
    """Test suite for normalize_timestamp_to_utc_z function"""

    def test_iso_format_with_z(self):
        """Test ISO format with Z suffix"""
        result = normalize_timestamp_to_utc_z("2024-01-15T10:30:00Z")
        assert result == "2024-01-15T10:30:00Z"

    def test_iso_format_with_timezone(self):
        """Test ISO format with timezone offset"""
        result = normalize_timestamp_to_utc_z("2024-01-15T10:30:00+05:00")
        assert result == "2024-01-15T05:30:00Z"

    def test_iso_format_without_timezone(self):
        """Test ISO format without timezone (assumes UTC)"""
        result = normalize_timestamp_to_utc_z("2024-01-15T10:30:00")
        assert result == "2024-01-15T10:30:00Z"

    def test_datetime_object_with_timezone(self):
        """Test datetime object with timezone"""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = normalize_timestamp_to_utc_z(dt)
        assert result == "2024-01-15T10:30:00Z"

    def test_datetime_object_without_timezone(self):
        """Test datetime object without timezone (assumes UTC)"""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = normalize_timestamp_to_utc_z(dt)
        assert result == "2024-01-15T10:30:00Z"

    def test_empty_string(self):
        """Test empty string returns None"""
        result = normalize_timestamp_to_utc_z("")
        assert result is None

    def test_none_value(self):
        """Test None value returns None"""
        result = normalize_timestamp_to_utc_z(None)
        assert result is None

    def test_nan_value(self):
        """Test NaN value returns None"""
        result = normalize_timestamp_to_utc_z(pd.NA)
        assert result is None

    def test_float_nan(self):
        """Test float NaN returns None"""
        result = normalize_timestamp_to_utc_z(float('nan'))
        assert result is None

    def test_invalid_string(self):
        """Test invalid string returns None"""
        result = normalize_timestamp_to_utc_z("not a timestamp")
        assert result is None

    def test_various_date_formats(self):
        """Test various common date formats"""
        test_cases = [
            ("2024/01/15 10:30:00", "2024-01-15T10:30:00Z"),
            ("01-15-2024 10:30:00", "2024-01-15T10:30:00Z"),
            ("15/01/2024 10:30:00", "2024-01-15T10:30:00Z"),
        ]
        for input_str, expected in test_cases:
            result = normalize_timestamp_to_utc_z(input_str)
            assert result is not None, f"Failed to parse: {input_str}"


class TestIsTimestampColumn:
    """Test suite for is_timestamp_column function"""

    def test_created_at_column(self):
        """Test column named 'created_at' is identified as timestamp"""
        result = is_timestamp_column("created_at", "2024-01-15T10:30:00Z")
        assert result is True

    def test_updated_at_column(self):
        """Test column named 'updated_at' is identified as timestamp"""
        result = is_timestamp_column("updated_at", "2024-01-15T10:30:00Z")
        assert result is True

    def test_closed_at_column(self):
        """Test column named 'closed_at' is identified as timestamp"""
        result = is_timestamp_column("closed_at", "2024-01-15T10:30:00Z")
        assert result is True

    def test_merged_at_column(self):
        """Test column named 'merged_at' is identified as timestamp"""
        result = is_timestamp_column("merged_at", "2024-01-15T10:30:00Z")
        assert result is True

    def test_commit_date_column(self):
        """Test column named 'commit_date' is identified as timestamp"""
        result = is_timestamp_column("commit_date", "2024-01-15T10:30:00Z")
        assert result is True

    def test_timestamp_column(self):
        """Test column named 'timestamp' is identified as timestamp"""
        result = is_timestamp_column("timestamp", "2024-01-15T10:30:00Z")
        assert result is True

    def test_non_timestamp_column_status(self):
        """Test column named 'status' is NOT identified as timestamp"""
        result = is_timestamp_column("status", "open")
        assert result is False

    def test_non_timestamp_column_path(self):
        """Test column named 'path' is NOT identified as timestamp"""
        result = is_timestamp_column("path", "/some/file/path")
        assert result is False

    def test_non_timestamp_column_author(self):
        """Test column named 'author' is NOT identified as timestamp"""
        result = is_timestamp_column("author", "John Doe")
        assert result is False

    def test_non_timestamp_column_url(self):
        """Test column named 'url' is NOT identified as timestamp"""
        result = is_timestamp_column("url", "https://example.com")
        assert result is False

    def test_non_timestamp_column_sha(self):
        """Test column named 'sha' is NOT identified as timestamp"""
        result = is_timestamp_column("sha", "abc123def456")
        assert result is False

    def test_column_with_timestamp_data(self):
        """Test column with timestamp-like data but no timestamp name"""
        result = is_timestamp_column("custom_field", "2024-01-15T10:30:00Z")
        assert result is True  # Timestamp pattern in data is detected

    def test_none_sample_data(self):
        """Test handling of None sample data"""
        result = is_timestamp_column("created_at", None)
        assert result is True  # Should still identify based on column name


class TestNormalizeTimestampsInDataframe:
    """Test suite for normalize_timestamps_in_dataframe function"""

    def test_single_timestamp_column(self):
        """Test DataFrame with single timestamp column"""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'created_at': [
                '2024-01-15T10:30:00+05:00',
                '2024-01-16T12:00:00Z',
                '2024-01-17T08:45:00'
            ]
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert result_df['created_at'][0] == '2024-01-15T05:30:00Z'
        assert result_df['created_at'][1] == '2024-01-16T12:00:00Z'
        assert result_df['created_at'][2] == '2024-01-17T08:45:00Z'
        assert 'created_at' in report
        assert report['created_at']['converted_count'] == 3

    def test_multiple_timestamp_columns(self):
        """Test DataFrame with multiple timestamp columns"""
        df = pd.DataFrame({
            'id': [1, 2],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z'],
            'updated_at': ['2024-01-15T11:00:00Z', '2024-01-16T13:00:00Z']
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert len(report) == 2
        assert 'created_at' in report
        assert 'updated_at' in report

    def test_mixed_columns(self):
        """Test DataFrame with mixed timestamp and non-timestamp columns"""
        df = pd.DataFrame({
            'id': [1, 2],
            'name': ['Alice', 'Bob'],
            'created_at': ['2024-01-15T10:30:00Z', '2024-01-16T12:00:00Z'],
            'status': ['open', 'closed']
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert len(report) == 1
        assert 'created_at' in report
        assert result_df['name'][0] == 'Alice'
        assert result_df['status'][1] == 'closed'

    def test_with_null_values(self):
        """Test DataFrame with null values in timestamp columns"""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'created_at': ['2024-01-15T10:30:00Z', None, '2024-01-17T08:45:00Z']
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert report['created_at']['converted_count'] == 2
        assert report['created_at']['failed_count'] == 0
        assert pd.isna(result_df['created_at'][1])

    def test_with_invalid_timestamps(self):
        """Test DataFrame with invalid timestamps"""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'created_at': ['2024-01-15T10:30:00Z', 'invalid', '2024-01-17T08:45:00Z']
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert report['created_at']['converted_count'] == 2
        assert report['created_at']['failed_count'] == 1

    def test_empty_dataframe(self):
        """Test empty DataFrame"""
        df = pd.DataFrame()

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert len(report) == 0
        assert len(result_df) == 0


class TestNormalizeTimestampsInFile:
    """Test suite for normalize_timestamps_in_file function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_normalize_csv_file(self, temp_dir):
        """Test normalizing a CSV file"""
        # Create test CSV
        test_file = os.path.join(temp_dir, 'test.csv')
        df = pd.DataFrame({
            'id': [1, 2],
            'created_at': ['2024-01-15T10:30:00+05:00', '2024-01-16T12:00:00Z']
        })
        df.to_csv(test_file, index=False)

        # Normalize
        success, report = normalize_timestamps_in_file(test_file, backup=False)

        # Verify
        assert success is True
        result_df = pd.read_csv(test_file)
        assert result_df['created_at'][0] == '2024-01-15T05:30:00Z'

    def test_backup_creation(self, temp_dir):
        """Test that backup file is created"""
        # Create test CSV
        test_file = os.path.join(temp_dir, 'test.csv')
        df = pd.DataFrame({
            'id': [1],
            'created_at': ['2024-01-15T10:30:00Z']
        })
        df.to_csv(test_file, index=False)

        # Normalize with backup
        success, report = normalize_timestamps_in_file(test_file, backup=True)

        # Verify backup exists
        assert success is True
        backup_file = os.path.join(temp_dir, 'test_backup.csv')
        assert os.path.exists(backup_file)

    def test_multiple_backups(self, temp_dir):
        """Test that multiple backups don't overwrite each other"""
        # Create test CSV
        test_file = os.path.join(temp_dir, 'test.csv')
        df = pd.DataFrame({
            'id': [1],
            'created_at': ['2024-01-15T10:30:00Z']
        })
        df.to_csv(test_file, index=False)

        # Create first backup manually
        backup1 = os.path.join(temp_dir, 'test_backup.csv')
        df.to_csv(backup1, index=False)

        # Normalize with backup (should create _backup_1.csv)
        success, report = normalize_timestamps_in_file(test_file, backup=True)

        # Verify second backup exists
        assert success is True
        backup2 = os.path.join(temp_dir, 'test_backup_1.csv')
        assert os.path.exists(backup2)

    def test_invalid_file(self, temp_dir):
        """Test handling of invalid file path"""
        invalid_file = os.path.join(temp_dir, 'nonexistent.csv')
        success, report = normalize_timestamps_in_file(invalid_file, backup=False)

        assert success is False


class TestFindAllTeams:
    """Test suite for find_all_teams function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory structure"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_find_existing_teams(self, temp_dir):
        """Test finding existing team folders"""
        # Create some team folders
        for i in [1, 5, 10]:
            os.makedirs(os.path.join(temp_dir, str(i)))

        # Find teams
        teams = find_all_teams(temp_dir)

        # Verify
        assert len(teams) == 3
        assert os.path.join(temp_dir, '1') in teams
        assert os.path.join(temp_dir, '5') in teams
        assert os.path.join(temp_dir, '10') in teams

    def test_no_teams(self, temp_dir):
        """Test when no team folders exist"""
        teams = find_all_teams(temp_dir)
        assert len(teams) == 0

    def test_all_teams_present(self, temp_dir):
        """Test when all 22 teams are present"""
        # Create all team folders
        for i in range(1, 23):
            os.makedirs(os.path.join(temp_dir, str(i)))

        # Find teams
        teams = find_all_teams(temp_dir)

        # Verify
        assert len(teams) == 22


class TestNormalizeTimestampsForAllTeams:
    """Test suite for normalize_timestamps_for_all_teams function"""

    @pytest.fixture
    def temp_dir_with_teams(self):
        """Set up temporary directory structure with test data"""
        temp_path = tempfile.mkdtemp()

        # Create team folders with CSV files
        for team_num in [1, 2, 3]:
            team_dir = os.path.join(temp_path, str(team_num))
            os.makedirs(team_dir)

            # Create test CSV in each team folder
            test_file = os.path.join(team_dir, f'data.csv')
            df = pd.DataFrame({
                'id': [1, 2],
                'created_at': ['2024-01-15T10:30:00+05:00', '2024-01-16T12:00:00Z']
            })
            df.to_csv(test_file, index=False)

            # Create subdirectory with another CSV (for recursive test)
            subdir = os.path.join(team_dir, 'subdir')
            os.makedirs(subdir)
            subfile = os.path.join(subdir, 'subdata.csv')
            df.to_csv(subfile, index=False)

        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_normalize_all_teams_recursive(self, temp_dir_with_teams):
        """Test normalizing all teams with recursive option"""
        # Normalize with recursive option
        normalize_timestamps_for_all_teams(temp_dir_with_teams, backup=False, recursive=True)

        # Verify files were normalized
        test_file = os.path.join(temp_dir_with_teams, '1', 'data.csv')
        df = pd.read_csv(test_file)
        assert df['created_at'][0] == '2024-01-15T05:30:00Z'

        # Verify subdirectory files were also normalized
        subfile = os.path.join(temp_dir_with_teams, '1', 'subdir', 'subdata.csv')
        df_sub = pd.read_csv(subfile)
        assert df_sub['created_at'][0] == '2024-01-15T05:30:00Z'

    def test_normalize_all_teams_non_recursive(self, temp_dir_with_teams):
        """Test normalizing all teams without recursive option"""
        # Normalize without recursive option
        normalize_timestamps_for_all_teams(temp_dir_with_teams, backup=False, recursive=False)

        # Verify main files were normalized
        test_file = os.path.join(temp_dir_with_teams, '1', 'data.csv')
        df = pd.read_csv(test_file)
        assert df['created_at'][0] == '2024-01-15T05:30:00Z'

        # Verify subdirectory files were NOT normalized
        subfile = os.path.join(temp_dir_with_teams, '1', 'subdir', 'subdata.csv')
        df_sub = pd.read_csv(subfile)
        # Should still have the original timezone offset
        assert df_sub['created_at'][0] == '2024-01-15T10:30:00+05:00'


class TestEdgeCases:
    """Test suite for edge cases and corner scenarios"""

    def test_dataframe_with_all_null_timestamps(self):
        """Test DataFrame where all timestamps are null"""
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'created_at': [None, None, None]
        })

        result_df, report = normalize_timestamps_in_dataframe(df)

        assert report['created_at']['converted_count'] == 0
        assert report['created_at']['failed_count'] == 0

    def test_very_old_date(self):
        """Test with a very old date"""
        result = normalize_timestamp_to_utc_z("1900-01-01T00:00:00Z")
        assert result == "1900-01-01T00:00:00Z"

    def test_future_date(self):
        """Test with a future date"""
        result = normalize_timestamp_to_utc_z("2100-12-31T23:59:59Z")
        assert result == "2100-12-31T23:59:59Z"

    def test_leap_year_date(self):
        """Test with leap year date"""
        result = normalize_timestamp_to_utc_z("2024-02-29T12:00:00Z")
        assert result == "2024-02-29T12:00:00Z"

    def test_column_name_case_insensitive(self):
        """Test that column name matching is case insensitive"""
        result1 = is_timestamp_column("CREATED_AT", "2024-01-15T10:30:00Z")
        result2 = is_timestamp_column("Created_At", "2024-01-15T10:30:00Z")
        result3 = is_timestamp_column("created_at", "2024-01-15T10:30:00Z")

        assert result1 is True
        assert result2 is True
        assert result3 is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])