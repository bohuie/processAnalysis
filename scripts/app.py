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


def calculate_top_file_changes(files: List[dict]) -> tuple:
    """Calculate the file with most changes and its percentage."""
    if not files:
        return None, 0.0
    
    total_changes = sum(f.get('changes', 0) for f in files)
    if total_changes == 0:
        return None, 0.0
    
    top_file = max(files, key=lambda f: f.get('changes', 0))
    top_file_changes = top_file.get('changes', 0)
    percentage = (top_file_changes / total_changes) * 100 if total_changes > 0 else 0.0
    
    return top_file.get('filename'), percentage


def check_documentation_updates(files: List[dict]) -> dict:
    """Check if documentation files were updated."""
    doc_patterns = ['.md', 'README', 'CHANGELOG', 'docs/', 'documentation/']
    
    has_readme = any('README' in f.get('filename', '').upper() for f in files)
    
    doc_files = [
        f for f in files 
        if any(pattern.lower() in f.get('filename', '').lower() for pattern in doc_patterns)
    ]
    
    return {
        'docs_updated': len(doc_files) > 0,
        'has_readme_changes': has_readme,
        'doc_files_count': len(doc_files)
    }


def get_unique_reviewers(pr: dict, extractor: PullRequestExtractor) -> List[str]:
    """Extract unique reviewers from PR reviews."""
    pr_id = pr.get('number')
    reviews = extractor.extract_pr_reviews(pr_id)
    
    reviewers = set()
    for review in reviews:
        user = review.get('user', {})
        if user and user.get('login'):
            reviewers.add(user['login'])
    
    # Remove the PR author from reviewers if present
    pr_author = pr.get('user', {}).get('login')
    reviewers.discard(pr_author)
    
    return list(reviewers)


def save_prs_to_csv(pull_requests: List[dict], extractor: PullRequestExtractor, filepath: Path):
    """Save pull requests to CSV file with correct column names and populated data."""
    if not pull_requests:
        print("[WARN] No pull requests to save")
        return
    
    print(f"[INFO] Saving {len(pull_requests)} PRs to CSV: {filepath}")
    
    # Updated fieldnames to match expected schema
    fieldnames = [
        'Action',
        'pr_id',
        'pr_title',
        'pr_author',
        'head_branch',
        'base_branch',
        'state',
        'created_at',
        'updated_at',
        'closed_at',
        'merged_at',
        'merged_by',
        'num_commits',
        'num_reviewers',
        'reviewers',
        'pr_description',
        'mergeable_state',
        'is_up_to_date',
        'was_up_to_date_at_merge',
        'has_conflicts',
        'is_self_merged',
        'line_added',
        'line_deleted',
        'total_changes',
        'files_changed',
        'was_behind_at_merge',
        'top_file',
        'top_file_change_%',
        'docs_updated',
        'has_readme_changes',
        'feature_documentation_status',
        'description'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for pr in pull_requests:
            pr_id = pr.get('number')
            pr_author = pr.get('user', {}).get('login') if pr.get('user') else None
            merged_by = pr.get('merged_by', {}).get('login') if pr.get('merged_by') else None
            
            # Get file changes for this PR
            print(f"[DEBUG] Fetching files for PR #{pr_id}")
            files = extractor.extract_pr_file_changes(pr_id)
            
            # Calculate metrics
            top_file, top_file_pct = calculate_top_file_changes(files)
            doc_info = check_documentation_updates(files)
            
            # Get reviewers
            reviewers = get_unique_reviewers(pr, extractor)
            
            # Calculate derived fields
            is_self_merged = (merged_by == pr_author) if merged_by and pr_author else False
            has_conflicts = pr.get('mergeable_state') in ['dirty', 'conflicting']
            
            # Determine feature documentation status
            feature_doc_status = 'N/A'
            if pr.get('merged_at'):
                if doc_info['docs_updated']:
                    feature_doc_status = 'Documented'
                else:
                    feature_doc_status = 'Not Documented'
            
            row = {
                'Action': '',  # Empty as per original schema
                'pr_id': pr_id,
                'pr_title': pr.get('title', ''),
                'pr_author': pr_author,
                'head_branch': pr.get('head', {}).get('ref') if pr.get('head') else None,
                'base_branch': pr.get('base', {}).get('ref') if pr.get('base') else None,
                'state': pr.get('state'),
                'created_at': pr.get('created_at'),
                'updated_at': pr.get('updated_at'),
                'closed_at': pr.get('closed_at'),
                'merged_at': pr.get('merged_at'),
                'merged_by': merged_by,
                'num_commits': pr.get('commits', 0),
                'num_reviewers': len(reviewers),
                'reviewers': ', '.join(reviewers) if reviewers else '',
                'pr_description': (pr.get('body', '') or '')[:500],
                'mergeable_state': pr.get('mergeable_state', ''),
                'is_up_to_date': '',  # Would need additional API call to determine
                'was_up_to_date_at_merge': '',  # Historical data not available
                'has_conflicts': has_conflicts,
                'is_self_merged': is_self_merged,
                'line_added': pr.get('additions', 0),
                'line_deleted': pr.get('deletions', 0),
                'total_changes': pr.get('additions', 0) + pr.get('deletions', 0),
                'files_changed': pr.get('changed_files', 0),
                'was_behind_at_merge': '',  # Historical data not available
                'top_file': top_file or '',
                'top_file_change_%': f"{top_file_pct:.2f}" if top_file else '',
                'docs_updated': doc_info['docs_updated'],
                'has_readme_changes': doc_info['has_readme_changes'],
                'feature_documentation_status': feature_doc_status,
                'description': (pr.get('body', '') or '')[:500],
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
        'pr_id', 'pr_author', 'commit_sha', 'commit_author', 'commit_date',
        'commit_message', 'additions', 'deletions', 'files_changed'
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
            stats = commit.get('stats', {})
            
            all_commits.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'commit_sha': commit.get('sha'),
                'commit_author': author_data.get('name', 'Unknown'),
                'commit_date': author_data.get('date'),
                'commit_message': commit_data.get('message', '').split('\n')[0][:200],
                'additions': stats.get('additions'),
                'deletions': stats.get('deletions'),
                'files_changed': len(commit.get('files', [])) if commit.get('files') else None,
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
        'pr_id', 'pr_author', 'commit_sha', 'filename', 'status', 'additions', 
        'deletions', 'changes', 'patch_snippet'
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
                    'additions': file.get('additions'),
                    'deletions': file.get('deletions'),
                    'changes': file.get('changes'),
                    'patch_snippet': (file.get('patch', '') or '')[:200],
                })
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_files)
    
    print(f"[SUCCESS] Saved {len(all_files)} file changes to: {filepath}")


def save_comments_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all comments from PRs to CSV - includes all review comment types."""
    if not pull_requests:
        print("[WARN] No pull requests to extract comments from")
        return
    
    print(f"[INFO] Extracting comments from {len(pull_requests)} PRs...")
    
    fieldnames = [
        'pr_id', 'pr_author', 'comment_type', 'comment_id', 'comment_author',
        'comment_body', 'created_at', 'updated_at', 'review_state'
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
                'comment_author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or '')[:500],
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                'review_state': comment.get('state', ''),
            })
        
        # Issue comments (general PR comments)
        for comment in comments.get('issue_comments', []):
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'issue',
                'comment_id': comment.get('id'),
                'comment_author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or '')[:500],
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                'review_state': '',
            })
        
        # Review summaries (from extract_pr_reviews)
        reviews = extractor.extract_pr_reviews(pr_id)
        for review in reviews:
            # Only add if there's a body (to avoid duplicates with review_comments)
            if review.get('body'):
                all_comments.append({
                    'pr_id': pr_id,
                    'pr_author': pr_author,
                    'comment_type': 'review_summary',
                    'comment_id': review.get('id'),
                    'comment_author': review.get('user', {}).get('login') if review.get('user') else 'Unknown',
                    'comment_body': (review.get('body', '') or '')[:500],
                    'created_at': review.get('submitted_at'),
                    'updated_at': review.get('submitted_at'),
                    'review_state': review.get('state', ''),
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
        
        results["pull_requests_extracted"] = len(pull_requests)
        print(f"[INFO] Extracted {len(pull_requests)} pull requests")

        # Save to JSON
        if save_json:
            json_filepath = json_dir / f"{repo_name}_pull_requests.json"
            save_prs_to_json(pull_requests, json_filepath)
            results["output_files"].append(f"PRs JSON: {json_filepath}")

        # Save to CSV
        if save_csv:
            # 1. Pull Requests CSV (now with corrected columns and populated data)
            csv_filepath = csv_dir / f"{repo_name}_pull_requests.csv"
            save_prs_to_csv(pull_requests, extractor, csv_filepath)
            results["output_files"].append(f"PRs CSV: {csv_filepath}")
            
            # 2. Commits CSV
            if include_commits:
                commits_filepath = csv_dir / f"{repo_name}_commits.csv"
                save_commits_to_csv(extractor, pull_requests, commits_filepath)
                results["output_files"].append(f"Commits CSV: {commits_filepath}")
            
            # 3. File Changes CSV
            if include_files:
                files_filepath = csv_dir / f"{repo_name}_file_changes.csv"
                save_file_changes_to_csv(extractor, pull_requests, files_filepath)
                results["output_files"].append(f"Files CSV: {files_filepath}")
            
            # 4. Comments CSV (now includes all review types)
            if include_comments:
                comments_filepath = csv_dir / f"{repo_name}_comments.csv"
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