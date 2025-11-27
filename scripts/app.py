import os
import sys
import json
import csv
import traceback
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Fix Python path to find src module
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")
print(f"[DEBUG] Python path: {sys.path[:3]}")

# Import extraction functionality
try:
    from src.extractors.pull_request_extractor import PullRequestExtractor
    print("[DEBUG] Successfully imported PullRequestExtractor")
except ImportError as e:
    print(f"[ERROR] Failed to import PullRequestExtractor: {e}")
    sys.exit(1)


def save_prs_to_csv(pull_requests: List[dict], filepath: Path):
    """Save pull requests to CSV file."""
    if not pull_requests:
        print("[WARN] No pull requests to save")
        return
    
    print(f"[INFO] Saving {len(pull_requests)} PRs to CSV: {filepath}")
    
    fieldnames = [
        'pr_id',
        'created_at',
        'merged_at',
        'pr_author',
        'pr_title',
        'pr_description',
        'merged_by',
        'state',
        'head_branch',
        'was_up_to_date_at_merge',
        'has_conflicts',
        'docs_updated',
        'num_reviewers'
    ]

    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for pr in pull_requests:
            row = {
                'pr_id': pr.get('number'),
                'created_at': pr.get('created_at'),
                'merged_at': pr.get('merged_at'),
                'pr_author': pr.get('user', {}).get('login') if pr.get('user') else None,
                'pr_title': pr.get('pr_title'),
                'pr_description': (pr.get('pr_description') or ''),
                'merged_by': pr.get('merged_by'),
                'state': pr.get('state'),
                'head_branch': pr.get('head', {}).get('ref') if pr.get('head') else None,
                'was_up_to_date_at_merge': pr.get('was_up_to_date_at_merge'),
                'has_conflicts': pr.get('has_conflicts'),
                'docs_updated': pr.get('docs_updated'),
                'num_reviewers': pr.get('num_reviewers'),
            }

            writer.writerow(row)
    
    print(f"[SUCCESS] CSV saved: {filepath}")


def save_commits_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all commits from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract commits from")
        return
    
    print(f"[INFO] Extracting commits from {len(pull_requests)} PRs...")
    
    fieldnames = [
        'pr_id', 'pr_author', 'commit_sha', 'author', 'commit_date',
        'commit_message', 'lines_added', 'lines_deleted', 'files_changed'
    ]
    
    all_commits = []
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        
        print(f"[DEBUG] Extracting commits for PR #{pr_id}")
        commits = extractor.extract_commits_from_pr(pr_id)
        
        for commit in commits:
            commit_data = commit.get('commit', {})
            author_data = commit_data.get('author', {})
            
            all_commits.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'commit_sha': commit.get('sha'),
                'author': author_data.get('name', 'Unknown'),
                'commit_date': author_data.get('date'),
                'commit_message': commit_data.get('message', '').split('\n')[0],
                'lines_added': None,  # Available in commit details
                'lines_deleted': None,  # Available in commit details
                'files_changed': None,  # Available in commit details
            })
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_commits)
    
    print(f"[SUCCESS] Saved {len(all_commits)} commits to: {filepath}")

def save_file_changes_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all file changes from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract file changes from")
        return
    
    print(f"[INFO] Extracting file changes from {len(pull_requests)} PRs...")
    
    fieldnames = [
        'pr_id', 'pr_author', 'commit_sha', 'filename', 'status', 'lines_added', 
        'lines_deleted', 'changes', 'patch_snippet'
    ]
    
    all_files = []
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        
        print(f"[DEBUG] Extracting commits and file changes for PR #{pr_id}")
        
        # Get all commits for this PR
        commits = extractor.extract_commits_from_pr(pr_id)
        
        # For each commit, get the file changes
        for commit in commits:
            commit_sha = commit.get('sha')
            
            # Get detailed commit info with files
            commit_details = extractor.extract_commit_details(commit_sha)
            files = commit_details.get('files', [])
            
            for file in files:
                all_files.append({
                    'pr_id': pr_id,
                    'pr_author': pr_author,
                    'commit_sha': commit_sha,
                    'filename': file.get('filename'),
                    'status': file.get('status'),
                    'lines_added': file.get('lines_added'),
                    'lines_deleted': file.get('lines_deleted'),
                    'changes': file.get('changes'),
                    'patch_snippet': (file.get('patch', '') or ''),
                })
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_files)
    
    print(f"[SUCCESS] Saved {len(all_files)} file changes to: {filepath}")

def save_comments_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all comments from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract comments from")
        return
    
    print(f"[INFO] Extracting comments from {len(pull_requests)} PRs...")
    
    fieldnames = [
        'pr_id', 'pr_author', 'comment_type', 'comment_id', 'author',
        'comment_body', 'created_at', 'updated_at'
    ]
    
    all_comments = []
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        
        print(f"[DEBUG] Extracting comments for PR #{pr_id}")
        comments = extractor.extract_pr_all_comments(pr_id)
        
        # Review comments (inline code comments)
        for comment in comments.get('review_comments', []):
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'review',
                'comment_id': comment.get('id'),
                'author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or ''),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
            })
        
        # Issue comments (general PR comments)
        for comment in comments.get('issue_comments', []):
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'issue',
                'comment_id': comment.get('id'),
                'author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or ''),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
            })
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_comments)
    
    print(f"[SUCCESS] Saved {len(all_comments)} comments to: {filepath}")


def save_prs_to_json(pull_requests: List[dict], filepath: Path):
    """Save pull requests to JSON file."""
    if not pull_requests:
        print("[WARN] No pull requests to save")
        return
    
    print(f"[INFO] Saving {len(pull_requests)} PRs to JSON: {filepath}")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(pull_requests, f, indent=2, default=str)
    
    print(f"[SUCCESS] JSON saved: {filepath}")


def extract_repository_data(
    repo_owner: str,
    repo_name: str,
    output_base_dir: str = "./data",
    save_json: bool = True,
    save_csv: bool = True,
    include_commits: bool = True,
    include_files: bool = True,
    include_comments: bool = True,
) -> dict:
    """Extract all data from a GitHub repository."""
    
    print("=" * 80)
    print(f"EXTRACTING: {repo_owner}/{repo_name}")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output directory: {output_base_dir}")
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
            print(f"[INFO] JSON output: {json_dir}")
        if save_csv:
            csv_dir.mkdir(parents=True, exist_ok=True)
            print(f"[INFO] CSV output: {csv_dir}")

        # Initialize extractor
        print("\n[INFO] Connecting to GitHub API...")
        extractor = PullRequestExtractor(
            repo_owner=repo_owner,
            repo_name=repo_name,
            need_auth=True,
        )

        # Extract pull requests
        print("[INFO] Fetching pull requests...")
        pull_requests = extractor.extract_all_pull_requests(state="all")
        
        # ===================== ENRICH PR DATA =====================
        print("[INFO] Enriching PR data...")

        enriched_prs = []

        for pr in pull_requests:
            pr_id = pr["number"]

            # 1. Fetch full PR details
            full = extractor.extract_pull_request_by_id(pr_id)
            if not full:
                enriched_prs.append(pr)
                continue

            # Add merged_by in a normalized format
            merged_by = full.get("merged_by")
            pr["merged_by"] = merged_by.get("login") if merged_by else None

            # Add mergeable_state
            pr["mergeable_state"] = full.get("mergeable_state")

            # 2. Determine conflicts
            pr["has_conflicts"] = (full.get("mergeable_state") == "dirty")

            # 3. Compute was_up_to_date_at_merge
            if full.get("merged_at"):
                base_sha = full["base"]["sha"]
                head_sha = full["head"]["sha"]

                comp = extractor.compare_commits(base_sha, head_sha)
                behind = comp.get("behind_by", None)
                pr["was_up_to_date_at_merge"] = (behind == 0)
            else:
                pr["was_up_to_date_at_merge"] = None

            # 4. Compute num_reviewers
            reviews = extractor.extract_pr_reviews(pr_id)
            reviewers = {r.get("user", {}).get("login") for r in reviews if r.get("user")}
            pr["num_reviewers"] = len(reviewers)

            # 5. docs_updated using file changes
            files = extractor.extract_pr_file_changes(pr_id)
            docs_updated = any(
                any(k in f.get("filename", "").lower() for k in ["readme", "doc", "docs"])
                for f in files
            )
            pr["docs_updated"] = docs_updated

            # 6. Title / description normalization
            pr["pr_title"] = full.get("title")
            pr["pr_description"] = full.get("body")

            enriched_prs.append(pr)

        pull_requests = enriched_prs

        
        results["pull_requests_extracted"] = len(pull_requests)
        print(f"[INFO] Extracted {len(pull_requests)} pull requests")

        # Save to JSON
        if save_json:
            json_filepath = json_dir / f"{repo_name}_all_pull_requests.json"
            save_prs_to_json(pull_requests, json_filepath)
            results["output_files"].append(f"PRs JSON: {json_filepath}")

        # Save to CSV
        if save_csv:
            # 1. Pull Requests CSV
            csv_filepath = csv_dir / f"{repo_name}_all_pull_requests.csv"
            save_prs_to_csv(pull_requests, csv_filepath)
            results["output_files"].append(f"PRs CSV: {csv_filepath}")
            
            # 2. Commits CSV
            if include_commits:
                commits_filepath = csv_dir / f"{repo_name}_PR_commits.csv"
                save_commits_to_csv(extractor, pull_requests, commits_filepath)
                results["output_files"].append(f"Commits CSV: {commits_filepath}")
            
            # 3. File Changes CSV
            if include_files:
                files_filepath = csv_dir / f"{repo_name}_commit_file_changes.csv"
                save_file_changes_to_csv(extractor, pull_requests, files_filepath)
                results["output_files"].append(f"Files CSV: {files_filepath}")
            
            # 4. Comments CSV
            if include_comments:
                comments_filepath = csv_dir / f"{repo_name}_review-comments.csv"
                save_comments_to_csv(extractor, pull_requests, comments_filepath)
                results["output_files"].append(f"Comments CSV: {comments_filepath}")

        results["status"] = "success"

        # Print success summary
        print("\n" + "=" * 80)
        print("EXTRACTION COMPLETE")
        print("=" * 80)
        print(f"Pull Requests: {len(pull_requests)}")
        if results["output_files"]:
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


if __name__ == "__main__":
    
    # ==================== CONFIGURATION ====================
    
    REPO_OWNER = "COSC-499-W2023" 
    REPO_NAME = "year-long-project-team-15"
    OUTPUT_DIR = "./data"
    SAVE_JSON = True
    SAVE_CSV = True
    INCLUDE_COMMITS = True
    INCLUDE_FILES = True
    INCLUDE_COMMENTS = True
    
    # ==================== EXECUTION ====================
    
    print("\n" + "=" * 80)
    print("GITHUB SINGLE REPOSITORY DATA EXTRACTION")
    print("=" * 80)
    print(f"Working directory: {Path.cwd()}")
    print(f"Script location: {Path(__file__).parent}")
    print("=" * 80)
    
    try:
        results = extract_repository_data(
            repo_owner=REPO_OWNER,
            repo_name=REPO_NAME,
            output_base_dir=OUTPUT_DIR,
            save_json=SAVE_JSON,
            save_csv=SAVE_CSV,
            include_commits=INCLUDE_COMMITS,
            include_files=INCLUDE_FILES,
            include_comments=INCLUDE_COMMENTS,
        )

        if results["status"] != "success":
            print("\n" + "=" * 80)
            print("❌ EXTRACTION FAILED")
            print("=" * 80)
            for error in results["errors"]:
                print(f"  Error: {error}")
            sys.exit(1)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)
        
    print("\n" + "=" * 80)
    print(f"✅ SUCCESS - Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)