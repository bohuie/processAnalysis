import os
import sys
import json
import csv
import traceback
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def enrich_single_pr(args) -> dict:
    """
    Enrich a single PR with additional data (used for parallel processing).
    
    Args:
        args: Tuple of (pr, extractor, file_changes_cache)
    
    Returns:
        Enriched PR dictionary
    """
    pr, extractor, file_changes_cache = args
    pr_id = pr["number"]
    
    try:
        # 1. Fetch full PR details
        full = extractor.extract_pull_request_by_id(pr_id)
        if not full:
            return pr
        
        # Add merged_by in normalized format
        merged_by = full.get("merged_by")
        pr["merged_by"] = merged_by.get("login") if merged_by else None
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
        
        # 5-6. Use cached file changes
        file_changes = file_changes_cache.get(pr_id, [])
        docs_updated = any(
            any(k in f.get("filename", "").lower() for k in ["readme", "doc", "docs"])
            for f in file_changes
        )
        pr["docs_updated"] = docs_updated
        
        total_added = sum(f.get("additions", 0) for f in file_changes)
        total_deleted = sum(f.get("deletions", 0) for f in file_changes)
        files_changed = len(file_changes)
        
        pr["lines_added"] = total_added
        pr["lines_deleted"] = total_deleted
        pr["files_changed"] = files_changed
        
        # 7. Title / description normalization
        pr["pr_title"] = full.get("title")
        pr["pr_description"] = full.get("body")
        
        return pr
    
    except Exception as e:
        print(f"[WARN] Error enriching PR #{pr_id}: {e}")
        return pr


def save_prs_to_csv(pull_requests: List[dict], filepath: Path):
    """Save pull requests to CSV file."""
    if not pull_requests:
        print("[WARN] No pull requests to save")
        return
    
    print(f"[INFO] Saving {len(pull_requests)} PRs to CSV: {filepath}")
    
    fieldnames = [
        'pr_id',
        'created_at',
        'updated_at',
        'closed_at',
        'merged_at',
        'pr_author',
        'pr_title',
        'pr_description',
        'merged_by',
        'state',
        'head_branch',
        'base_branch',
        'was_up_to_date_at_merge',
        'has_conflicts',
        'docs_updated',
        'num_reviewers',
        'lines_added',
        'lines_deleted',
        'files_changed'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for pr in pull_requests:
            row = {
                'pr_id': pr.get('number'),
                'created_at': pr.get('created_at'),
                'updated_at': pr.get('updated_at'),
                'closed_at': pr.get('closed_at'),
                'merged_at': pr.get('merged_at'),
                'pr_author': pr.get('user', {}).get('login') if pr.get('user') else None,
                'pr_title': pr.get('pr_title'),
                'pr_description': (pr.get('pr_description') or ''),
                'merged_by': pr.get('merged_by'),
                'state': pr.get('state'),
                'head_branch': pr.get('head', {}).get('ref') if pr.get('head') else None,
                'base_branch': pr.get('base', {}).get('ref') if pr.get('base') else None,
                'was_up_to_date_at_merge': pr.get('was_up_to_date_at_merge'),
                'has_conflicts': pr.get('has_conflicts'),
                'docs_updated': pr.get('docs_updated'),
                'num_reviewers': pr.get('num_reviewers'),
                'lines_added': pr.get('lines_added'),
                'lines_deleted': pr.get('lines_deleted'),
                'files_changed': pr.get('files_changed'),
            }

            writer.writerow(row)
    
    print(f"[SUCCESS] CSV saved: {filepath}")


def save_commits_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):

    if not pull_requests:
        print("[WARN] No pull requests to extract commits from")
        return

    print(f"[INFO] Extracting commit-level rows from {len(pull_requests)} PRs...")

    fieldnames = [
        'pr_id',
        'commit_sha',
        'commit_message',
        'commit_date',
        'lines_added',     
        'lines_deleted',   
        'author',
        'pr_author'
    ]

    all_rows = []

    for pr_idx, pr in enumerate(pull_requests, 1):
        if pr_idx % max(1, len(pull_requests) // 10) == 0:
            print(f"[INFO] Progress: {pr_idx}/{len(pull_requests)} PRs processed for commits...")
        
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'

        commits = extractor.extract_commits_from_pr(pr_id)

        for commit in commits:
            commit_sha = commit.get("sha")
            commit_data = commit.get("commit", {})
            author_data = commit_data.get("author", {})

            commit_message = commit_data.get("message", "").split("\n")[0]
            commit_date = author_data.get("date")

            # GitHub username of commit author
            # 1. Try GitHub user object
            api_author = commit.get("author")

            # 2. If GitHub user is missing, fall back to raw commit name
            if isinstance(api_author, dict) and api_author.get("login"):
                commit_author_login = api_author["login"]
            else:
                # Fallback: use commit.commit.author.name
                raw_author = commit.get("commit", {}).get("author", {})
                commit_author_login = raw_author.get("name", "Unknown")


            commit_details = extractor.extract_commit_details(commit_sha)
            stats = commit_details.get("stats", {})

            total_added = stats.get("additions", 0)
            total_deleted = stats.get("deletions", 0)

            all_rows.append({
                "pr_id": pr_id,
                "commit_sha": commit_sha,
                "commit_message": commit_message,
                "commit_date": commit_date,
                "lines_added": total_added,
                "lines_deleted": total_deleted,
                "author": commit_author_login,
                "pr_author": pr_author,
            })

    # Write CSV
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[SUCCESS] Saved {len(all_rows)} commit rows to: {filepath}")



def save_file_changes_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all file changes from PRs to CSV."""
    if not pull_requests:
        print("[WARN] No pull requests to extract file changes from")
        return

    print(f"[INFO] Extracting file changes from {len(pull_requests)} PRs...")

    fieldnames = [
        'pr_id',
        'pr_author',
        'commit_sha',
        'author',           
        'file_path',
        'status',
        'lines_added',
        'lines_deleted',
        'changes',
        'patch_snippet'
    ]

    all_files = []

    for pr_idx, pr in enumerate(pull_requests, 1):
        if pr_idx % max(1, len(pull_requests) // 10) == 0:
            print(f"[INFO] Progress: {pr_idx}/{len(pull_requests)} PRs processed for file changes...")
        
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'

        # Get all commits for this PR
        commits = extractor.extract_commits_from_pr(pr_id)

        for commit in commits:
            commit_sha = commit.get('sha')

            # --- Author resolution: same strategy as save_commits_to_csv ---
            api_author = commit.get("author")

            if isinstance(api_author, dict) and api_author.get("login"):
                commit_author = api_author["login"]
            else:
                raw_author = commit.get("commit", {}).get("author", {})
                commit_author = raw_author.get("name", "Unknown")

            # --- Safely fetch commit details (for files only) ---
            commit_details = extractor.extract_commit_details(commit_sha) or {}
            files = commit_details.get('files') or []

            for file in files:
                all_files.append({
                    'pr_id': pr_id,
                    'pr_author': pr_author,
                    'commit_sha': commit_sha,
                    'author': commit_author,
                    'file_path': file.get('filename'),
                    'status': file.get('status'),
                    'lines_added': file.get('additions'),
                    'lines_deleted': file.get('deletions'),
                    'changes': file.get('changes'),
                    'patch_snippet': (file.get('patch', '') or '')
                })


    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_files)

    print(f"[SUCCESS] Saved {len(all_files)} file changes to: {filepath}")


def save_comments_to_csv(extractor: PullRequestExtractor, pull_requests: List[dict], filepath: Path):
    """Extract and save all comments from PRs to CSV, including raw review states."""
    if not pull_requests:
        print("[WARN] No pull requests to extract comments from")
        return
    
    print(f"[INFO] Extracting comments from {len(pull_requests)} PRs...")
    
    fieldnames = [
        'pr_id',
        'pr_author',
        'comment_type',
        'comment_id',
        'author',
        'comment_body',
        'created_at',
        'updated_at',
        'state',        # NEW COLUMN
    ]
    
    all_comments = []
    
    for pr_idx, pr in enumerate(pull_requests, 1):
        if pr_idx % max(1, len(pull_requests) // 10) == 0:
            print(f"[INFO] Progress: {pr_idx}/{len(pull_requests)} PRs processed for comments...")
        
        pr_id = pr.get('number')
        pr_author = pr.get('user', {}).get('login') if pr.get('user') else 'Unknown'
        
        comments = extractor.extract_pr_all_comments(pr_id)

        # Build review_id -> state map from /pulls/{pr}/reviews
        reviews = comments.get('pr_reviews', [])
        review_state = {
            r.get('id'): (r.get('state') or "")
            for r in reviews
        }
        
        # 1) Review comments (inline code comments)
        for comment in comments.get('review_comments', []):
            parent_review_id = comment.get('pull_request_review_id')
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'inline',
                'comment_id': comment.get('id'),
                'author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or ''),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                # state copied from parent review if known, otherwise blank
                'state': review_state.get(parent_review_id, ""),
            })
        
        # 2) Issue comments (PR conversation tab comments)
        for comment in comments.get('issue_comments', []):
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'conversation',
                'comment_id': comment.get('id'),
                'author': comment.get('user', {}).get('login') if comment.get('user') else 'Unknown',
                'comment_body': (comment.get('body', '') or ''),
                'created_at': comment.get('created_at'),
                'updated_at': comment.get('updated_at'),
                # GitHub doesn't expose a review state here → leave blank (no remap)
                'state': "",
            })
            
        # 3) Review objects (when reviewer clicks "Review changes")
        for review in reviews:
            all_comments.append({
                'pr_id': pr_id,
                'pr_author': pr_author,
                'comment_type': 'review',
                'comment_id': review.get('id'),
                'author': review.get('user', {}).get('login') if review.get('user') else 'Unknown',
                'comment_body': (review.get('body', '') or ''),
                'created_at': review.get('submitted_at'),
                'updated_at': review.get('submitted_at'),
                # raw GitHub state: APPROVED / CHANGES_REQUESTED / COMMENTED / DISMISSED / etc.
                'state': (review.get('state') or ""),
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
        
        # Pre-cache file changes for all PRs to avoid redundant API calls
        print("[INFO] Pre-caching file changes for all PRs...")
        file_changes_cache = {}
        for pr in pull_requests:
            pr_id = pr["number"]
            file_changes_cache[pr_id] = extractor.extract_pr_file_changes(pr_id)
        
        print(f"[INFO] Cached file changes for {len(file_changes_cache)} PRs")
        
        # Parallel PR enrichment using ThreadPoolExecutor
        print("[INFO] Starting parallel PR enrichment with 5 workers...")
        max_workers = min(5, len(pull_requests))  # Use up to 5 threads
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all enrichment tasks
            futures = [
                executor.submit(enrich_single_pr, (pr, extractor, file_changes_cache))
                for pr in pull_requests
            ]
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(futures):
                try:
                    enriched_pr = future.result()
                    enriched_prs.append(enriched_pr)
                    completed += 1
                    if completed % max(1, len(pull_requests) // 10) == 0:
                        print(f"[INFO] Enrichment progress: {completed}/{len(pull_requests)} PRs")
                except Exception as e:
                    print(f"[WARN] Failed to enrich PR: {e}")
        
        print(f"[INFO] Completed enrichment for {len(enriched_prs)} PRs")
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
    REPO_NAMES = [
        #"year-long-project-team-2",
        #"year-long-project-team-8",
        #"year-long-project-team-9",
        #"year-long-project-team-10",
        #"year-long-project-team-11",
        #"year-long-project-team-12",
        "year-long-project-team-15",
        "year-long-project-team-19"
    ]
    OUTPUT_DIR = "./data"
    SAVE_JSON = True
    SAVE_CSV = True
    INCLUDE_COMMITS = True
    INCLUDE_FILES = True
    INCLUDE_COMMENTS = True
    
    # ==================== EXECUTION ====================
    
    print("\n" + "=" * 80)
    print("GITHUB MULTIPLE REPOSITORY DATA EXTRACTION")
    print("=" * 80)
    print(f"Working directory: {Path.cwd()}")
    print(f"Script location: {Path(__file__).parent}")
    print(f"Total repositories to process: {len(REPO_NAMES)}")
    print("=" * 80)
    
    all_results = []
    failed_repos = []
    
    try:
        for idx, repo_name in enumerate(REPO_NAMES, 1):
            print(f"\n[{idx}/{len(REPO_NAMES)}] Processing: {repo_name}")
            
            try:
                results = extract_repository_data(
                    repo_owner=REPO_OWNER,
                    repo_name=repo_name,
                    output_base_dir=OUTPUT_DIR,
                    save_json=SAVE_JSON,
                    save_csv=SAVE_CSV,
                    include_commits=INCLUDE_COMMITS,
                    include_files=INCLUDE_FILES,
                    include_comments=INCLUDE_COMMENTS,
                )
                
                all_results.append(results)
                
                if results["status"] != "success":
                    failed_repos.append((repo_name, results["errors"]))
            
            except Exception as e:
                print(f"[ERROR] Failed to process {repo_name}: {e}")
                failed_repos.append((repo_name, [str(e)]))
                traceback.print_exc()
        
        # Print summary
        print("\n" + "=" * 80)
        print("EXTRACTION SUMMARY")
        print("=" * 80)
        print(f"Total repositories processed: {len(all_results)}")
        print(f"Successful: {len([r for r in all_results if r['status'] == 'success'])}")
        print(f"Failed: {len(failed_repos)}")
        
        if failed_repos:
            print("\n❌ FAILED REPOSITORIES:")
            for repo_name, errors in failed_repos:
                print(f"\n  {repo_name}:")
                for error in errors:
                    print(f"    - {error}")
            sys.exit(1)
        else:
            print("\n✅ ALL REPOSITORIES SUCCESSFULLY EXTRACTED")
        
        print("=" * 80)

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()
        sys.exit(1)
        
    print("\n" + "=" * 80)
    print(f"✅ SUCCESS - Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)