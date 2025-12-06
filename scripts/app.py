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


def save_prs_to_csv(pull_requests: List[dict], extractor: PullRequestExtractor, filepath: Path):
    """Save pull requests to CSV file with correct column names and populated data."""
    if not pull_requests:
        print("[WARN] No pull requests to save")
        return
    
    print(f"[INFO] Saving {len(pull_requests)} PRs to CSV: {filepath}")
    
    # Fieldnames matching the "Previous" schema
    fieldnames = [
        'pr_id',
        'title',
        'state',
        'author',
        'created_at',
        'updated_at',
        'closed_at',
        'merged_at',
        'merged_by',
        'head_branch',
        'base_branch',
        'commits',
        'additions',
        'deletions',
        'changed_files',
        'comments',
        'review_comments',
        'mergeable_state',
        'body'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for pr in pull_requests:
            pr_id = pr.get('number')
            
            # Get comment counts
            all_comments = extractor.extract_pr_all_comments(pr_id)
            review_comments_count = len(all_comments.get('review_comments', []))
            issue_comments_count = len(all_comments.get('issue_comments', []))
            
            row = {
                'pr_id': pr_id,
                'title': pr.get('title', ''),
                'state': pr.get('state'),
                'author': pr.get('user', {}).get('login') if pr.get('user') else None,
                'created_at': pr.get('created_at'),
                'updated_at': pr.get('updated_at'),
                'closed_at': pr.get('closed_at'),
                'merged_at': pr.get('merged_at'),
                'merged_by': pr.get('merged_by', {}).get('login') if pr.get('merged_by') else None,
                'head_branch': pr.get('head', {}).get('ref') if pr.get('head') else None,
                'base_branch': pr.get('base', {}).get('ref') if pr.get('base') else None,
                'commits': pr.get('commits', 0),
                'additions': pr.get('additions', 0),
                'deletions': pr.get('deletions', 0),
                'changed_files': pr.get('changed_files', 0),
                'comments': issue_comments_count,
                'review_comments': review_comments_count,
                'mergeable_state': pr.get('mergeable_state', ''),
                'body': (pr.get('body', '') or '')[:1000],
            }
            writer.writerow(row)
    
    print(f"[SUCCESS] CSV saved: {filepath}")


def save_commits_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all commits from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract commits from")
        return
    
    print(f"[INFO] Extracting commits from {len(pull_requests)} PRs...")
    
    # Fieldnames matching the "Previous" schema
    fieldnames = [
        'repo_name',
        'pr_id',
        'pr_author',
        'head_branch',
        'base_branch',
        'commit_sha',
        'author',
        'commit_date',
        'file_path',
        'lines_added',
        'lines_deleted',
        'commit_message',
        'message_word_count'
    ]
    
    all_commits = []
    repo_name = f"{extractor.repo_owner}/{extractor.repo_name}"
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        head_branch = pr.get('head', {}).get('ref') if pr.get('head') else None
        base_branch = pr.get('base', {}).get('ref') if pr.get('base') else None
        
        print(f"[DEBUG] Extracting commits for PR #{pr_id}")
        commits = extractor.extract_commits_from_pr(pr_id)
        
        for commit in commits:
            commit_sha = commit.get('sha')
            commit_data = commit.get('commit', {})
            author_data = commit_data.get('author', {})
            commit_message = commit_data.get('message', '')
            
            # Get detailed commit info to get file changes
            commit_details = extractor.extract_commit_details(commit_sha)
            files = commit_details.get('files', [])
            
            # If there are files, create one row per file
            if files:
                for file in files:
                    all_commits.append({
                        'repo_name': repo_name,
                        'pr_id': pr_id,
                        'pr_author': pr_author,
                        'head_branch': head_branch,
                        'base_branch': base_branch,
                        'commit_sha': commit_sha,
                        'author': author_data.get('name', 'Unknown'),
                        'commit_date': author_data.get('date'),
                        'file_path': file.get('filename'),
                        'lines_added': file.get('additions', 0),
                        'lines_deleted': file.get('deletions', 0),
                        'commit_message': commit_message.split('\n')[0][:200],
                        'message_word_count': len(commit_message.split()),
                    })
            else:
                # If no files, still create a row without file info
                all_commits.append({
                    'repo_name': repo_name,
                    'pr_id': pr_id,
                    'pr_author': pr_author,
                    'head_branch': head_branch,
                    'base_branch': base_branch,
                    'commit_sha': commit_sha,
                    'author': author_data.get('name', 'Unknown'),
                    'commit_date': author_data.get('date'),
                    'file_path': None,
                    'lines_added': 0,
                    'lines_deleted': 0,
                    'commit_message': commit_message.split('\n')[0][:200],
                    'message_word_count': len(commit_message.split()),
                })
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_commits)
    
    print(f"[SUCCESS] Saved {len(all_commits)} commit records to: {filepath}")


def save_file_changes_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all file changes from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract file changes from")
        return
    
    print(f"[INFO] Extracting file changes from {len(pull_requests)} PRs...")
    
    # Fieldnames matching the "Previous" schema
    fieldnames = [
        'repo_name',
        'pr_id',
        'pr_author',
        'head_branch',
        'base_branch',
        'commit_sha',
        'commit_author',
        'commit_date',
        'commit_message',
        'file_path',
        'file_status',
        'lines_added',
        'lines_deleted',
        'total_changes',
        'previous_filename'
    ]
    
    all_files = []
    repo_name = f"{extractor.repo_owner}/{extractor.repo_name}"
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        head_branch = pr.get('head', {}).get('ref') if pr.get('head') else None
        base_branch = pr.get('base', {}).get('ref') if pr.get('base') else None
        
        print(f"[DEBUG] Extracting commits and file changes for PR #{pr_id}")
        
        # Get all commits for this PR
        commits = extractor.extract_commits_from_pr(pr_id)
        
        # For each commit, get the file changes
        for commit in commits:
            commit_sha = commit.get('sha')
            commit_data = commit.get('commit', {})
            author_data = commit_data.get('author', {})
            commit_message = commit_data.get('message', '')
            
            # Get detailed commit info with files
            commit_details = extractor.extract_commit_details(commit_sha)
            files = commit_details.get('files', [])
            
            for file in files:
                all_files.append({
                    'repo_name': repo_name,
                    'pr_id': pr_id,
                    'pr_author': pr_author,
                    'head_branch': head_branch,
                    'base_branch': base_branch,
                    'commit_sha': commit_sha,
                    'commit_author': author_data.get('name', 'Unknown'),
                    'commit_date': author_data.get('date'),
                    'commit_message': commit_message.split('\n')[0][:200],
                    'file_path': file.get('filename'),
                    'file_status': file.get('status'),
                    'lines_added': file.get('additions', 0),
                    'lines_deleted': file.get('deletions', 0),
                    'total_changes': file.get('changes', 0),
                    'previous_filename': file.get('previous_filename', ''),
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
    
    # Fieldnames matching the "Previous" schema
    fieldnames = [
        'pr_id',
        'comment_id',
        'pr_author',
        'author',
        'comment_body',
        'comment_word_count',
        'created_at',
        'updated_at',
        'user_login',
        'state',
        'order_of_review'
    ]
    
    all_comments = []
    
    for pr in pull_requests:
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        
        print(f"[DEBUG] Extracting comments for PR #{pr_id}")
        comments = extractor.extract_pr_all_comments(pr_id)
        
        order_counter = 1
        
        # Review comments (inline code comments)
        for comment in comments.get('review_comments', []):
            comment_body = comment.get('body', '') or ''
            comment_author = comment.get('user', {}).get('login') if comment.get('user') else 'Unknown'
            
            all_comments.append({
                'pr_id': pr_id,
                'comment_id': comment.get('id'),
                'pr_author': pr_author,
                'author': comment_author,
                'comment_body': comment_body[:500],
                'comment_word_count': len(comment_body.split()),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                'user_login': comment_author,
                'state': comment.get('state', ''),
                'order_of_review': order_counter,
            })
            order_counter += 1
        
        # Issue comments (general PR comments)
        for comment in comments.get('issue_comments', []):
            comment_body = comment.get('body', '') or ''
            comment_author = comment.get('user', {}).get('login') if comment.get('user') else 'Unknown'
            
            all_comments.append({
                'pr_id': pr_id,
                'comment_id': comment.get('id'),
                'pr_author': pr_author,
                'author': comment_author,
                'comment_body': comment_body[:500],
                'comment_word_count': len(comment_body.split()),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                'user_login': comment_author,
                'state': '',
                'order_of_review': order_counter,
            })
            order_counter += 1
        
        # Review summaries (from extract_pr_reviews)
        reviews = extractor.extract_pr_reviews(pr_id)
        for review in reviews:
            # Only add if there's a body (to avoid duplicates with review_comments)
            if review.get('body'):
                comment_body = review.get('body', '') or ''
                comment_author = review.get('user', {}).get('login') if review.get('user') else 'Unknown'
                
                all_comments.append({
                    'pr_id': pr_id,
                    'comment_id': review.get('id'),
                    'pr_author': pr_author,
                    'author': comment_author,
                    'comment_body': comment_body[:500],
                    'comment_word_count': len(comment_body.split()),
                    'created_at': review.get('submitted_at'),
                    'updated_at': review.get('submitted_at'),
                    'user_login': comment_author,
                    'state': review.get('state', ''),
                    'order_of_review': order_counter,
                })
                order_counter += 1
    
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