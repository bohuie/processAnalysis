import os
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import shutil

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the function to test
from process_model.clean import clean_and_impute_branch_names


class TestCleanAndImputeBranchNames:
    """Test suite for clean_and_impute_branch_names function"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    @pytest.fixture
    def sample_data_with_missing_branches(self):
        """Create sample data with missing branch names"""
        return pd.DataFrame({
            'pr_id': [1, 1, 1, 2, 2, 3, 3, 3],
            'branch_name': ['feature-a', np.nan, np.nan, 'feature-b', np.nan, np.nan, np.nan, 'feature-c'],
            'commit_sha': ['abc1', 'abc2', 'abc3', 'def1', 'def2', 'ghi1', 'ghi2', 'ghi3'],
            'author': ['user1', 'user1', 'user2', 'user3', 'user3', 'user4', 'user4', 'user4']
        })

    @pytest.fixture
    def sample_data_all_branches_present(self):
        """Create sample data with all branch names present"""
        return pd.DataFrame({
            'pr_id': [1, 1, 2, 2, 3, 3],
            'branch_name': ['feature-a', 'feature-a', 'feature-b', 'feature-b', 'feature-c', 'feature-c'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2', 'ghi1', 'ghi2'],
            'author': ['user1', 'user1', 'user2', 'user2', 'user3', 'user3']
        })

    @pytest.fixture
    def sample_data_with_empty_strings(self):
        """Create sample data with empty string branch names"""
        return pd.DataFrame({
            'pr_id': [1, 1, 2, 2],
            'branch_name': ['feature-a', '', '', 'feature-b'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2'],
            'author': ['user1', 'user1', 'user2', 'user2']
        })

    @pytest.fixture
    def sample_data_with_float_pr_ids(self):
        """Create sample data with float PR IDs (e.g., 283.0)"""
        return pd.DataFrame({
            'pr_id': [283.0, 283.0, 284.0, 284.0],
            'branch_name': ['feature-a', np.nan, np.nan, 'feature-b'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2'],
            'author': ['user1', 'user1', 'user2', 'user2']
        })

    def test_basic_imputation(self, temp_dir, sample_data_with_missing_branches):
        """Test basic branch name imputation"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Save sample data
        sample_data_with_missing_branches.to_csv(input_path, index=False)
        
        # Run cleaning
        clean_and_impute_branch_names(input_path, output_path)
        
        # Load and verify results
        result_df = pd.read_csv(output_path)
        
        # Check that missing values were imputed
        assert result_df['branch_name'].isna().sum() == 0
        
        # Verify correct imputation
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert all(pr1_rows['branch_name'] == 'feature-a')
        
        pr2_rows = result_df[result_df['pr_id'] == 2]
        assert all(pr2_rows['branch_name'] == 'feature-b')
        
        pr3_rows = result_df[result_df['pr_id'] == 3]
        assert all(pr3_rows['branch_name'] == 'feature-c')

    def test_no_imputation_needed(self, temp_dir, sample_data_all_branches_present):
        """Test when all branch names are already present"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        sample_data_all_branches_present.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Verify no changes were made
        assert result_df['branch_name'].isna().sum() == 0
        assert len(result_df) == len(sample_data_all_branches_present)

    def test_empty_string_conversion(self, temp_dir, sample_data_with_empty_strings):
        """Test that empty strings are converted to NaN and then imputed"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        sample_data_with_empty_strings.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Verify empty strings were imputed
        assert result_df['branch_name'].isna().sum() == 0
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert all(pr1_rows['branch_name'] == 'feature-a')

    def test_float_pr_id_conversion(self, temp_dir, sample_data_with_float_pr_ids):
        """Test that float PR IDs (like 283.0) are converted to integers"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        sample_data_with_float_pr_ids.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Verify PR IDs are integers (or Int64)
        assert result_df['pr_id'].dtype in [np.int64, pd.Int64Dtype(), 'Int64']
        
        # Verify imputation still works correctly
        pr283_rows = result_df[result_df['pr_id'] == 283]
        assert all(pr283_rows['branch_name'] == 'feature-a')

    def test_missing_pr_id_column(self, temp_dir):
        """Test handling when pr_id column is missing"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create data without pr_id column
        df = pd.DataFrame({
            'branch_name': ['feature-a', 'feature-b'],
            'commit_sha': ['abc1', 'def1']
        })
        df.to_csv(input_path, index=False)
        
        # Should handle gracefully and not crash
        clean_and_impute_branch_names(input_path, output_path)
        
        # Output file should not be created
        assert not os.path.exists(output_path)

    def test_missing_branch_name_column(self, temp_dir):
        """Test handling when branch_name column is missing"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create data without branch_name column
        df = pd.DataFrame({
            'pr_id': [1, 2, 3],
            'commit_sha': ['abc1', 'def1', 'ghi1']
        })
        df.to_csv(input_path, index=False)
        
        # Should handle gracefully and not crash
        clean_and_impute_branch_names(input_path, output_path)
        
        # Output file should not be created
        assert not os.path.exists(output_path)

    def test_empty_file(self, temp_dir):
        """Test handling of empty CSV file"""
        input_path = os.path.join(temp_dir, 'empty.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create empty file
        with open(input_path, 'w') as f:
            f.write('')
        
        # Should handle gracefully
        clean_and_impute_branch_names(input_path, output_path)
        
        # Output file should not be created
        assert not os.path.exists(output_path)

    def test_nonexistent_file(self, temp_dir):
        """Test handling of nonexistent input file"""
        input_path = os.path.join(temp_dir, 'nonexistent.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Should handle gracefully
        clean_and_impute_branch_names(input_path, output_path)
        
        # Output file should not be created
        assert not os.path.exists(output_path)

    def test_output_directory_creation(self, temp_dir):
        """Test that output directory is created if it doesn't exist"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_subdir = os.path.join(temp_dir, 'nested', 'output', 'dir')
        output_path = os.path.join(output_subdir, 'output.csv')
        
        # Create sample data
        df = pd.DataFrame({
            'pr_id': [1, 1],
            'branch_name': ['feature-a', np.nan],
            'commit_sha': ['abc1', 'abc2']
        })
        df.to_csv(input_path, index=False)
        
        # Output directory doesn't exist yet
        assert not os.path.exists(output_subdir)
        
        # Run cleaning
        clean_and_impute_branch_names(input_path, output_path)
        
        # Verify directory was created
        assert os.path.exists(output_subdir)
        assert os.path.exists(output_path)

    def test_multiple_branch_names_per_pr(self, temp_dir):
        """Test when a PR has different branch names (uses first one)"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create data where PR 1 has two different branch names
        df = pd.DataFrame({
            'pr_id': [1, 1, 1, 1],
            'branch_name': ['feature-a', 'feature-b', np.nan, np.nan],
            'commit_sha': ['abc1', 'abc2', 'abc3', 'abc4'],
            'author': ['user1', 'user1', 'user2', 'user2']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Should use the first branch name encountered
        pr1_missing = result_df[(result_df['pr_id'] == 1) & 
                                (result_df['commit_sha'].isin(['abc3', 'abc4']))]
        # The missing values should be filled with 'feature-a' (first value)
        assert all(pr1_missing['branch_name'] == 'feature-a')

    def test_all_missing_branches_for_pr(self, temp_dir):
        """Test when all rows for a PR have missing branch names"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        df = pd.DataFrame({
            'pr_id': [1, 1, 2, 2],
            'branch_name': [np.nan, np.nan, 'feature-b', np.nan],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2'],
            'author': ['user1', 'user1', 'user2', 'user2']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # PR 1 should still have missing values (no valid branch to impute from)
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert pr1_rows['branch_name'].isna().all()
        
        # PR 2 should be imputed
        pr2_rows = result_df[result_df['pr_id'] == 2]
        assert all(pr2_rows['branch_name'] == 'feature-b')

    def test_preserves_other_columns(self, temp_dir, sample_data_with_missing_branches):
        """Test that other columns are preserved unchanged"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        sample_data_with_missing_branches.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        original_df = pd.read_csv(input_path)
        
        # Verify other columns unchanged
        assert list(result_df['commit_sha']) == list(original_df['commit_sha'])
        assert list(result_df['author']) == list(original_df['author'])

    def test_large_dataset(self, temp_dir):
        """Test with a larger dataset"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create a larger dataset
        data = []
        for pr_id in range(1, 101):  # 100 PRs
            for commit_num in range(1, 11):  # 10 commits each
                branch_name = f'feature-{pr_id}' if commit_num == 1 else np.nan
                data.append({
                    'pr_id': pr_id,
                    'branch_name': branch_name,
                    'commit_sha': f'sha-{pr_id}-{commit_num}',
                    'author': f'user-{pr_id}'
                })
        
        df = pd.DataFrame(data)
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Verify all missing values were imputed
        assert result_df['branch_name'].isna().sum() == 0
        
        # Verify total rows preserved
        assert len(result_df) == 1000  # 100 PRs * 10 commits

    def test_mixed_data_types_in_pr_id(self, temp_dir):
        """Test handling of mixed data types in pr_id column"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        # Create data with string PR IDs that can be converted to integers
        df = pd.DataFrame({
            'pr_id': ['1', '1', '2', '2'],
            'branch_name': ['feature-a', np.nan, np.nan, 'feature-b'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Should handle conversion and imputation
        assert result_df['branch_name'].isna().sum() == 0

    def test_nan_in_pr_id(self, temp_dir):
        """Test handling when pr_id itself has NaN values"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        df = pd.DataFrame({
            'pr_id': [1, 1, np.nan, np.nan],
            'branch_name': ['feature-a', np.nan, 'feature-b', np.nan],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        # Rows with valid pr_id should be imputed
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert all(pr1_rows['branch_name'] == 'feature-a')
        
        # Rows with NaN pr_id cannot be imputed
        nan_pr_rows = result_df[result_df['pr_id'].isna()]
        assert len(nan_pr_rows) == 2


class TestBatchProcessing:
    """Test suite for batch processing scenarios"""

    @pytest.fixture
    def temp_dir_with_team_files(self):
        """Create temporary directory with multiple team files"""
        temp_path = tempfile.mkdtemp()
        
        # Create input directory structure
        input_dir = os.path.join(temp_path, 'csv')
        os.makedirs(input_dir)
        
        # Create sample files for teams 2-4
        for team_id in range(2, 5):
            filename = f'code_structure_branching_labels_year-long-project-team-{team_id}_anonymized.csv'
            filepath = os.path.join(input_dir, filename)
            
            df = pd.DataFrame({
                'pr_id': [1, 1, 2, 2],
                'branch_name': ['feature-a', np.nan, np.nan, 'feature-b'],
                'commit_sha': ['abc1', 'abc2', 'def1', 'def2']
            })
            df.to_csv(filepath, index=False)
        
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_batch_processing_multiple_teams(self, temp_dir_with_team_files):
        """Test processing multiple team files"""
        input_dir = os.path.join(temp_dir_with_team_files, 'csv')
        output_dir = os.path.join(temp_dir_with_team_files, 'csv', 'clean')
        
        # Process teams 2-4
        for team_id in range(2, 5):
            input_filename = f'code_structure_branching_labels_year-long-project-team-{team_id}_anonymized.csv'
            input_path = os.path.join(input_dir, input_filename)
            output_path = os.path.join(output_dir, input_filename)
            
            clean_and_impute_branch_names(input_path, output_path)
        
        # Verify all output files were created
        for team_id in range(2, 5):
            output_filename = f'code_structure_branching_labels_year-long-project-team-{team_id}_anonymized.csv'
            output_path = os.path.join(output_dir, output_filename)
            assert os.path.exists(output_path)
            
            # Verify content
            result_df = pd.read_csv(output_path)
            assert result_df['branch_name'].isna().sum() == 0


class TestEdgeCases:
    """Test suite for edge cases"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path, ignore_errors=True)

    def test_single_row_file(self, temp_dir):
        """Test file with only one row"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        df = pd.DataFrame({
            'pr_id': [1],
            'branch_name': ['feature-a'],
            'commit_sha': ['abc1']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        assert len(result_df) == 1
        assert result_df['branch_name'][0] == 'feature-a'

    def test_unicode_branch_names(self, temp_dir):
        """Test handling of unicode characters in branch names"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        df = pd.DataFrame({
            'pr_id': [1, 1, 2, 2],
            'branch_name': ['feature-αβγ', np.nan, np.nan, 'feature-日本語'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2']
        })
        df.to_csv(input_path, index=False, encoding='utf-8')
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path, encoding='utf-8')
        
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert all(pr1_rows['branch_name'] == 'feature-αβγ')
        
        pr2_rows = result_df[result_df['pr_id'] == 2]
        assert all(pr2_rows['branch_name'] == 'feature-日本語')

    def test_special_characters_in_branch_names(self, temp_dir):
        """Test branch names with special characters"""
        input_path = os.path.join(temp_dir, 'input.csv')
        output_path = os.path.join(temp_dir, 'output.csv')
        
        df = pd.DataFrame({
            'pr_id': [1, 1, 2, 2],
            'branch_name': ['feature/fix-bug', np.nan, np.nan, 'hotfix-2024.01.15'],
            'commit_sha': ['abc1', 'abc2', 'def1', 'def2']
        })
        df.to_csv(input_path, index=False)
        
        clean_and_impute_branch_names(input_path, output_path)
        
        result_df = pd.read_csv(output_path)
        
        pr1_rows = result_df[result_df['pr_id'] == 1]
        assert all(pr1_rows['branch_name'] == 'feature/fix-bug')


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])