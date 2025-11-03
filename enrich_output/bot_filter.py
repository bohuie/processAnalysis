# fixed_timestamp_normalizer.py
import os
import pandas as pd
import glob
import re
from datetime import datetime, timezone
from dateutil import parser as date_parser

def normalize_timestamp_to_utc_z(timestamp_str):
    """
    Convert any timestamp format to UTC with Z suffix.
    Returns None if conversion fails.
    """
    if pd.isna(timestamp_str) or timestamp_str == '' or timestamp_str is None:
        return None
    
    # Handle NaN, NaT, and other pandas missing values
    if isinstance(timestamp_str, (float, int)) and pd.isna(timestamp_str):
        return None
    
    try:
        # If it's already a datetime object
        if isinstance(timestamp_str, datetime):
            dt = timestamp_str
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        # Convert string to datetime
        dt = date_parser.parse(str(timestamp_str))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    except Exception as e:
        print(f"    ⚠️  Could not parse timestamp: '{timestamp_str}' - {e}")
        return None

def is_timestamp_column(column_name, sample_data):
    """
    Determine if a column contains timestamp data.
    Improved to avoid false positives.
    """
    column_name_lower = column_name.lower()
    
    # Check column name for timestamp indicators (more specific)
    timestamp_keywords = [
        'created_at', 'updated_at', 'closed_at', 'merged_at', 
        'commit_date', 'date', 'timestamp'
    ]
    
    # Columns that should NOT be treated as timestamps
    non_timestamp_keywords = [
        'path', 'status', 'state', 'mergeable', 'up_to_date', 'self_merged',
        'behind', 'docs', 'documentation', 'file_', 'author', 'user', 'login',
        'message', 'title', 'description', 'body', 'url', 'html_url', 'diff_url',
        'patch_url', 'sha', 'node_id', 'id', 'number', 'comments', 'review_comments',
        'commits', 'additions', 'deletions', 'changed_files', 'labels', 'milestone',
        'locked', 'active_lock_reason', 'draft', 'head', 'base', 'auto_merge',
        'assignee', 'assignees', 'requested_reviewers', 'requested_teams'
    ]
    
    # First, exclude columns that are definitely not timestamps
    if any(non_timestamp in column_name_lower for non_timestamp in non_timestamp_keywords):
        return False
    
    # Then, include columns that are likely timestamps
    if any(timestamp_keyword in column_name_lower for timestamp_keyword in timestamp_keywords):
        return True
    
    # Check sample data for timestamp patterns (more strict)
    if sample_data is not None and len(sample_data) > 0:
        sample_str = str(sample_data)
        
        # More specific timestamp patterns
        timestamp_patterns = [
            r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}',  # ISO format at start
            r'^\d{4}/\d{2}/\d{2}[T ]\d{2}:\d{2}:\d{2}',  # Slash format at start
            r'^\d{2}-\d{2}-\d{4}[T ]\d{2}:\d{2}:\d{2}',  # DD-MM-YYYY at start
            r'^\d{2}/\d{2}/\d{4}[T ]\d{2}:\d{2}:\d{2}',  # MM/DD/YYYY at start
            r'^\w{3} \d{1,2} \d{2}:\d{2}:\d{2} \d{4}',   # Mon DD HH:MM:SS YYYY at start
        ]
        
        for pattern in timestamp_patterns:
            if re.search(pattern, sample_str):
                return True
    
    return False

def normalize_timestamps_in_dataframe(df):
    """
    Normalize all timestamp columns in a DataFrame to UTC Z format.
    Returns the modified DataFrame and a report of changes.
    """
    timestamp_columns = []
    conversion_report = {}
    
    # Identify timestamp columns
    for col in df.columns:
        # Get a non-null sample to check
        sample_data = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
        
        if is_timestamp_column(col, sample_data):
            timestamp_columns.append(col)
            conversion_report[col] = {
                'original_sample': sample_data,
                'converted_count': 0,
                'failed_count': 0
            }
    
    # Convert timestamp columns
    for col in timestamp_columns:
        print(f"    ⏰ Processing: {col}")
        
        original_non_null = df[col].notna().sum()
        
        # Apply normalization
        df[col] = df[col].apply(normalize_timestamp_to_utc_z)
        
        new_non_null = df[col].notna().sum()
        failed_count = original_non_null - new_non_null
        
        conversion_report[col]['converted_count'] = new_non_null
        conversion_report[col]['failed_count'] = failed_count
        
        # Get a converted sample
        converted_sample = df[col].dropna().iloc[0] if not df[col].dropna().empty else "No valid timestamps"
        conversion_report[col]['converted_sample'] = converted_sample
        
        print(f"      ✅ Converted: {new_non_null}, Failed: {failed_count}")
    
    return df, conversion_report

def normalize_timestamps_in_file(file_path, backup=True):
    """
    Normalize all timestamps in a CSV file to UTC Z format.
    
    Args:
        file_path: Path to the CSV file
        backup: Whether to create a backup file
    """
    try:
        print(f"\n📄 Processing: {os.path.basename(file_path)}")
        
        # Create backup if requested
        if backup:
            backup_path = file_path.replace('.csv', '_backup.csv')
            # Ensure we don't overwrite existing backup
            counter = 1
            while os.path.exists(backup_path):
                backup_path = file_path.replace('.csv', f'_backup_{counter}.csv')
                counter += 1
            
            import shutil
            shutil.copy2(file_path, backup_path)
            print(f"    💾 Backup created: {os.path.basename(backup_path)}")
        
        # Read CSV file
        df = pd.read_csv(file_path)
        original_shape = df.shape
        
        print(f"    📊 Original data: {original_shape[0]} rows, {original_shape[1]} columns")
        
        # Normalize timestamps
        df, report = normalize_timestamps_in_dataframe(df)
        
        # Save the normalized file
        df.to_csv(file_path, index=False)
        
        # Print summary
        print(f"    ✅ Saved normalized file")
        
        # Detailed report
        if report:
            print(f"    📋 Timestamp Conversion Report:")
            for col, stats in report.items():
                print(f"      └─ {col}:")
                print(f"         Original: {stats['original_sample']}")
                print(f"         Converted: {stats['converted_sample']}")
                print(f"         Success: {stats['converted_count']}, Failed: {stats['failed_count']}")
        
        return True, report
        
    except Exception as e:
        print(f"    ❌ Error processing {file_path}: {e}")
        return False, {}

def find_all_teams(base_path="../data/csv"):
    team_folders = []
    
    # Look for teams 1-22
    for team_num in range(1, 23):  # 1 to 22
        team_folder = f"{team_num}"
        team_path = os.path.join(base_path, team_folder)
        
        if os.path.exists(team_path) and os.path.isdir(team_path):
            team_folders.append(team_path)
        else:
            print(f"⚠️  Team folder not found: {team_path}")
    
    return team_folders

def normalize_timestamps_for_all_teams(base_path="../data/csv", backup=True, recursive=True):
    
    # Find all team folders
    team_folders = find_all_teams(base_path)
    
    if not team_folders:
        print(f"❌ No team folders found in: {base_path}")
        return
    
    total_files = 0
    successful_files = 0
    all_reports = {}
    
    print("🕒 CSV Timestamp Normalizer - All Teams")
    print("=" * 60)
    print(f"📁 Base path: {base_path}")
    print(f"🏁 Found {len(team_folders)} team folders")
    print(f"💾 Backup: {'ENABLED' if backup else 'DISABLED'}")
    print(f"📁 Recursive: {'ENABLED' if recursive else 'DISABLED'}")
    print("=" * 60)
    
    for team_folder in sorted(team_folders):
        team_name = os.path.basename(team_folder)
        print(f"\n🏁 Processing: {team_name}")
        print("-" * 40)
        
        team_files = 0
        team_successful = 0
        
        if recursive:
            # Walk through all subdirectories in the team folder
            for root, dirs, files in os.walk(team_folder):
                csv_files = [f for f in files if f.lower().endswith('.csv')]
                
                for csv_file in csv_files:
                    file_path = os.path.join(root, csv_file)
                    total_files += 1
                    team_files += 1
                    success, report = normalize_timestamps_in_file(file_path, backup)
                    if success:
                        successful_files += 1
                        team_successful += 1
                        all_reports[file_path] = report
        else:
            # Process only the team folder itself
            csv_files = glob.glob(os.path.join(team_folder, "*.csv"))
            for csv_file in csv_files:
                if os.path.isfile(csv_file):
                    total_files += 1
                    team_files += 1
                    success, report = normalize_timestamps_in_file(csv_file, backup)
                    if success:
                        successful_files += 1
                        team_successful += 1
                        all_reports[csv_file] = report
        
        print(f"  ✅ Team {team_name}: {team_successful}/{team_files} files successful")
    
    # Final summary
    print("\n" + "=" * 60)
    print("📊 NORMALIZATION SUMMARY")
    print("=" * 60)
    print(f"📁 Base path: {base_path}")
    print(f"🏁 Teams processed: {len(team_folders)}")
    print(f"📄 Total files processed: {total_files}")
    print(f"✅ Successful files: {successful_files}")
    print(f"❌ Failed files: {total_files - successful_files}")
    
    # Count total timestamp columns processed
    total_timestamp_columns = 0
    total_conversions = 0
    total_failures = 0
    
    for file_report in all_reports.values():
        for col_report in file_report.values():
            total_timestamp_columns += 1
            total_conversions += col_report.get('converted_count', 0)
            total_failures += col_report.get('failed_count', 0)
    
    print(f"⏰ Total timestamp columns found: {total_timestamp_columns}")
    print(f"🔄 Total timestamps converted: {total_conversions}")
    print(f"⚠️  Total conversion failures: {total_failures}")
    print("=" * 60)
    
    # List all teams processed
    print("\n🏁 TEAMS PROCESSED:")
    for team_folder in sorted(team_folders):
        team_name = os.path.basename(team_folder)
        print(f"  ✅ {team_name}")

if __name__ == "__main__":
    normalize_timestamps_for_all_teams("../data/csv", backup=True, recursive=True)