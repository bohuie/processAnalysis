import os
import sys
import traceback
from pathlib import Path
from typing import List # Not strictly needed, but kept for clarity in case you re-add batch functionality
from datetime import datetime

# Import extraction functionality
from src.extractors.pull_request_extractor import PullRequestExtractor


def extract_repository_data(
    repo_owner: str,
    repo_name: str,
    output_base_dir: str = "./data",
    save_json: bool = True,
    save_csv: bool = True,
    include_orphan_commits: bool = True,
    branch_for_orphans: str = "master",
    exclude_readme: bool = False,
) -> dict:
    """
    Extract all data from a GitHub repository.
    
    Args:
        repo_owner: GitHub organization or username
        repo_name: Repository name
        output_base_dir: Where to save the data
        save_json: Save data as JSON files
        save_csv: Save data as CSV files
        include_orphan_commits: Include commits not in any PR
        branch_for_orphans: Which branch to scan for orphan commits
        exclude_readme: Exclude README from log/weekly PRs
    
    Returns:
        Dictionary with extraction results
    """
    
    print("=" * 80)
    print(f"EXTRACTING: {repo_owner}/{repo_name}")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output directory: {output_base_dir}")
    print(f"Include orphan commits: {include_orphan_commits}")
    print(f"Exclude README from log PRs: {exclude_readme}")
    print("=" * 80)

    results = {
        "repo_name": repo_name,
        "status": "in_progress",
        "pull_requests_extracted": 0,
        "output_files": [],
        "errors": []
    }

    try:
        # Create output directories
        base_path = Path(output_base_dir).resolve()
        json_dir = base_path / "json" / repo_name
        csv_dir = base_path / "csv" / repo_name
        
        if save_json:
            json_dir.mkdir(parents=True, exist_ok=True)
        if save_csv:
            csv_dir.mkdir(parents=True, exist_ok=True)

        # Initialize extractor
        print("\n[INFO] Connecting to GitHub API...")
        extractor = PullRequestExtractor(
            repo_owner=repo_owner,
            repo_name=repo_name,
            need_auth=True,
            exclude_readme=exclude_readme,
        )

        # Extract all pull requests
        print("[INFO] Fetching pull requests...")
        pull_requests = extractor.extract_pull_requests_with_pagination(
            pull_request_status="all",
            save_data_to_json=save_json,
            save_data_to_csv=save_csv,
            csv_filename=f"{repo_name}_all_pull_requests",
            include_orphan_commits=include_orphan_commits,
            branch_for_orphans=branch_for_orphans
        )

        results["pull_requests_extracted"] = len(pull_requests)

        # Record output files
        if save_csv:
            if hasattr(extractor, 'csv_filepath') and extractor.csv_filepath:
                results["output_files"].append(f"PRs: {extractor.csv_filepath}")
            
            if hasattr(extractor, 'commit_csv_filepath') and extractor.commit_csv_filepath:
                results["output_files"].append(f"Commits: {extractor.commit_csv_filepath}")
            
            # This check includes the commit_file_changes_csv_filepath which was missing in the second duplicated function
            if hasattr(extractor, 'commit_file_changes_csv_filepath') and extractor.commit_file_changes_csv_filepath:
                results["output_files"].append(f"File Changes: {extractor.commit_file_changes_csv_filepath}")
            
            if hasattr(extractor, 'review_comments_csv_filepath') and extractor.review_comments_csv_filepath:
                results["output_files"].append(f"Comments: {extractor.review_comments_csv_filepath}")

        if save_json:
            results["output_files"].append(f"JSON: {json_dir}/")

        results["status"] = "success"

        # Print success summary
        print("\n" + "=" * 80)
        print("EXTRACTION COMPLETE")
        print("=" * 80)
        print(f"Pull Requests: {len(pull_requests)}")
        print(f"\nOutput files:")
        for filepath in results["output_files"]:
            print(f"  ✓ {filepath}")
        print("=" * 80)

    except Exception as e:
        results["status"] = "failed"
        results["errors"].append(str(e))
        print(f"\n[ERROR] Extraction failed: {e}")
        traceback.print_exc()

    return results


# ==================== MAIN EXECUTION - SINGLE REPO ONLY ====================

if __name__ == "__main__":
    
    # ==================== CONFIGURATION ====================
    
    # --- REQUIRED ---
    # GitHub organization/user (Set this to the correct owner name)
    REPO_OWNER = "COSC-499-W2023" 
    
    # Repository name to extract
    REPO_NAME = "year-long-project-team-15"
    
    # --- OPTIONS ---
    # Where to save extracted data
    OUTPUT_DIR = "./data"
    
    # Extraction options
    SAVE_JSON = True               # Save raw JSON data
    SAVE_CSV = True                # Save CSV files
    INCLUDE_ORPHANS = True         # Include commits not in PRs
    ORPHAN_BRANCH = "master"       # Branch to scan for orphans
    EXCLUDE_README = False         # Exclude README from log/weekly PRs
    
    # ==================== DATA EXTRACTION START ====================
    
    print("\n" + "=" * 80)
    print("GITHUB SINGLE REPOSITORY DATA EXTRACTION")
    print("=" * 80)
    
    try:
        results = extract_repository_data(
            repo_owner=REPO_OWNER,
            repo_name=REPO_NAME,
            output_base_dir=OUTPUT_DIR,
            save_json=SAVE_JSON,
            save_csv=SAVE_CSV,
            include_orphan_commits=INCLUDE_ORPHANS,
            branch_for_orphans=ORPHAN_BRANCH,
            exclude_readme=EXCLUDE_README,
        )

        if results["status"] != "success":
            print("\n" + "=" * 80)
            print("❌ EXTRACTION FAILED")
            print("=" * 80)
            sys.exit(1)

    except Exception as e:
        print(f"\n[FATAL ERROR] Script failed before extraction completed: {e}")
        sys.exit(1)
        
    print("\n" + "=" * 80)
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)