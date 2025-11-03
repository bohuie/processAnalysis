"""
OPTIMIZED CSV File Fixer for GitHub Extractor
Fixes issues in bulk with caching, batch processing, and parallel execution
"""

import os
import csv
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
from dateutil import parser
import requests
from dotenv import load_dotenv
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


class OptimizedCSVFixer:
    """Optimized CSV fixer with caching and batch processing."""
    
    # Batch processing settings
    BATCH_SIZE = 50  # Process commits in batches
    MAX_WORKERS = 10  # Parallel API calls
    CACHE_EXPIRY = 3600  # 1 hour cache
    
    def __init__(self, github_token: Optional[str] = None, repo_owner: str = None, repo_name: str = None):
        load_dotenv()
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}
        
        # Caching for API responses
        self.commit_cache = {}
        self.pr_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        print(f"[INFO] Initialized Optimized CSV Fixer")
        if self.repo_owner and self.repo_name:
            print(f"[INFO] Repository: {repo_owner}/{repo_name}")
        print(f"[INFO] Authentication: {'Yes' if self.github_token else 'No (limited)'}")
        print(f"[INFO] Parallel workers: {self.MAX_WORKERS}")
    
    def _make_request(self, url: str) -> Optional[requests.Response]:
        """Make API request with basic error handling."""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                time.sleep(1)  # Brief pause for rate limit
            return None
        except Exception as e:
            return None
    
    def _fetch_commit_details_batch(self, commit_shas: List[str]) -> Dict[str, Dict]:
        """Fetch multiple commit details in parallel."""
        if not self.repo_owner or not self.repo_name:
            return {}
        
        results = {}
        
        # Check cache first
        uncached_shas = []
        for sha in commit_shas:
            if sha in self.commit_cache:
                results[sha] = self.commit_cache[sha]
                self.cache_hits += 1
            else:
                uncached_shas.append(sha)
                self.cache_misses += 1
        
        if not uncached_shas:
            return results
        
        # Fetch uncached commits in parallel
        def fetch_one(sha):
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/{sha}"
            response = self._make_request(url)
            if response:
                data = response.json()
                self.commit_cache[sha] = data
                return (sha, data)
            return (sha, None)
        
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_one, sha) for sha in uncached_shas]
            
            for future in futures:
                try:
                    sha, data = future.result(timeout=30)
                    if data:
                        results[sha] = data
                except Exception:
                    pass
        
        return results
    
    def _fetch_reviewers_batch(self, pr_ids: List[int]) -> Dict[int, List[str]]:
        """Fetch reviewers for multiple PRs in parallel."""
        if not self.repo_owner or not self.repo_name:
            return {}
        
        results = {}
        
        # Check cache
        uncached_prs = []
        for pr_id in pr_ids:
            cache_key = f"pr_{pr_id}_reviewers"
            if cache_key in self.pr_cache:
                results[pr_id] = self.pr_cache[cache_key]
                self.cache_hits += 1
            else:
                uncached_prs.append(pr_id)
                self.cache_misses += 1
        
        if not uncached_prs:
            return results
        
        def fetch_pr_reviewers(pr_id):
            reviewers = set()
            
            # Review comments
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/comments"
            response = self._make_request(url)
            if response:
                for comment in response.json():
                    user = comment.get('user', {})
                    if user.get('login'):
                        reviewers.add(user['login'])
            
            # Issue comments
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_id}/comments"
            response = self._make_request(url)
            if response:
                for comment in response.json():
                    user = comment.get('user', {})
                    if user.get('login'):
                        reviewers.add(user['login'])
            
            # Get PR author to exclude
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}"
            response = self._make_request(url)
            if response:
                pr_author = response.json().get('user', {}).get('login')
                reviewers.discard(pr_author)
            
            return (pr_id, sorted(list(reviewers)))
        
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_pr_reviewers, pr_id) for pr_id in uncached_prs]
            
            for future in futures:
                try:
                    pr_id, reviewers = future.result(timeout=30)
                    results[pr_id] = reviewers
                    self.pr_cache[f"pr_{pr_id}_reviewers"] = reviewers
                except Exception:
                    pass
        
        return results
    
    def fix_commits_csv_optimized(self, input_file: str, output_file: Optional[str] = None) -> str:
        """Optimized commit CSV fixing with batch processing."""
        print(f"\n[INFO] Fixing commits CSV (OPTIMIZED): {input_file}")
        
        if output_file is None:
            input_path = Path(input_file)
            output_file = str(input_path.parent / f"{input_path.stem}_fixed{input_path.suffix}")
        
        # Read input
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames)
        
        total_rows = len(rows)
        print(f"[INFO] Processing {total_rows} rows")
        
        # Group rows by commit SHA for batch processing
        sha_to_rows = {}
        for idx, row in enumerate(rows):
            sha = row.get('commit_sha', '')
            if sha:
                if sha not in sha_to_rows:
                    sha_to_rows[sha] = []
                sha_to_rows[sha].append(idx)
        
        unique_shas = list(sha_to_rows.keys())
        print(f"[INFO] Found {len(unique_shas)} unique commits")
        
        # Process in batches
        fixed_rows = rows.copy()
        
        for i in range(0, len(unique_shas), self.BATCH_SIZE):
            batch_shas = unique_shas[i:i+self.BATCH_SIZE]
            print(f"[BATCH {i//self.BATCH_SIZE + 1}/{(len(unique_shas)-1)//self.BATCH_SIZE + 1}] Processing {len(batch_shas)} commits...")
            
            commit_data = self._fetch_commit_details_batch(batch_shas)
            
            # Apply fixes to all rows with these commits
            for sha in batch_shas:
                if sha not in commit_data:
                    continue
                
                data = commit_data[sha]
                
                # Extract common data
                commit_date_str = data.get('commit', {}).get('committer', {}).get('date')
                commit_date = parser.parse(commit_date_str).isoformat() if commit_date_str else ""
                
                author = data.get('author', {}).get('login', 'Unknown')
                if author == 'Unknown':
                    author = data.get('commit', {}).get('author', {}).get('name', 'Unknown')
                
                files = data.get('files', [])
                
                # Update all rows with this commit
                for row_idx in sha_to_rows[sha]:
                    row = fixed_rows[row_idx]
                    
                    # Fix date and author
                    if not row.get('commit_date', '').strip():
                        row['commit_date'] = commit_date
                    if not row.get('author', '').strip() or row['author'] in ['Unknown', 'Dana]-3aa5']:
                        row['author'] = author
                    
                    # Fix file data if missing
                    if not row.get('file_path', '').strip() and files:
                        first_file = files[0]
                        row['file_path'] = first_file.get('filename', '')
                        row['lines_added'] = str(first_file.get('additions', 0))
                        row['lines_deleted'] = str(first_file.get('deletions', 0))
        
        # Write output
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(fixed_rows)
        
        print(f"[INFO] ✓ Fixed CSV saved to: {output_file}")
        print(f"[CACHE] Hits: {self.cache_hits}, Misses: {self.cache_misses}")
        
        return output_file
    
    def fix_pr_csv_optimized(self, input_file: str, output_file: Optional[str] = None) -> str:
        """Optimized PR CSV fixing with batch processing."""
        print(f"\n[INFO] Fixing PR CSV (OPTIMIZED): {input_file}")
        
        if output_file is None:
            input_path = Path(input_file)
            output_file = str(input_path.parent / f"{input_path.stem}_fixed{input_path.suffix}")
        
        # Read input
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
        
        print(f"[INFO] Processing {len(rows)} PRs")
        
        # Add missing columns
        new_fieldnames = list(fieldnames)
        for col in ['is_up_to_date', 'has_conflicts', 'reviewers', 'num_reviewers']:
            if col not in new_fieldnames:
                idx = new_fieldnames.index('description') if 'description' in new_fieldnames else len(new_fieldnames)
                new_fieldnames.insert(idx, col)
        
        # Process rows
        fixed_rows = []
        
        # Batch fetch reviewers for PRs that need them
        prs_needing_reviewers = []
        for row in rows:
            if not row.get('reviewers', '').strip() or row.get('num_reviewers', '') == '0':
                pr_id = row.get('pr_id', '')
                if pr_id:
                    try:
                        prs_needing_reviewers.append(int(pr_id))
                    except:
                        pass
        
        if prs_needing_reviewers:
            print(f"[INFO] Fetching reviewers for {len(prs_needing_reviewers)} PRs...")
            reviewers_map = self._fetch_reviewers_batch(prs_needing_reviewers)
        else:
            reviewers_map = {}
        
        # Fix each row
        for row in tqdm(rows, desc="Fixing PR rows"):
            # Fix is_up_to_date
            if 'is_up_to_date' not in row or not row.get('is_up_to_date', '').strip():
                was_behind = row.get('was_behind_at_merge', '')
                if was_behind != '':
                    try:
                        row['is_up_to_date'] = str(int(was_behind) == 0)
                    except:
                        row['is_up_to_date'] = row.get('was_up_to_date_at_merge', '')
            
            # Fix has_conflicts
            if 'has_conflicts' not in row or not row.get('has_conflicts', '').strip():
                mergeable_state = row.get('mergeable_state', '').lower()
                if mergeable_state in ['dirty', 'conflicting', 'unstable']:
                    row['has_conflicts'] = 'True'
                elif mergeable_state in ['clean', 'mergeable']:
                    row['has_conflicts'] = 'False'
            
            # Fix reviewers
            pr_id_str = row.get('pr_id', '')
            try:
                pr_id = int(pr_id_str)
                if pr_id in reviewers_map:
                    reviewers = reviewers_map[pr_id]
                    row['reviewers'] = ', '.join(reviewers)
                    row['num_reviewers'] = str(len(reviewers))
            except:
                pass
            
            fixed_rows.append(row)
        
        # Write output
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            writer.writerows(fixed_rows)
        
        print(f"[INFO] ✓ Fixed PR CSV saved to: {output_file}")
        return output_file
    
    def scan_and_fix_all_repos(self, base_directory: str = "./data/csv") -> Dict:
        """Scan and fix all repos with optimized batch processing."""
        base_path = Path(base_directory)
        
        if not base_path.exists():
            print(f"[ERROR] Directory does not exist: {base_path}")
            return {"error": "Directory not found"}
        
        print("\n" + "="*80)
        print("OPTIMIZED BATCH CSV FIXER")
        print("="*80)
        print(f"Base directory: {base_path.resolve()}")
        print(f"Parallel workers: {self.MAX_WORKERS}")
        print(f"Batch size: {self.BATCH_SIZE}")
        
        repo_dirs = [d for d in base_path.iterdir() if d.is_dir()]
        
        if not repo_dirs:
            print(f"[WARN] No subdirectories found")
            return {"repos_scanned": 0, "files_fixed": 0}
        
        print(f"Found {len(repo_dirs)} repositories")
        print("="*80)
        
        summary = {
            "repos_scanned": 0,
            "repos_fixed": 0,
            "total_files_fixed": 0,
            "repo_details": [],
            "start_time": time.time()
        }
        
        for repo_dir in sorted(repo_dirs):
            repo_name = repo_dir.name
            print(f"\n{'='*80}")
            print(f"REPOSITORY: {repo_name}")
            print(f"{'='*80}")
            
            summary["repos_scanned"] += 1
            
            # Update repo context
            self.repo_name = repo_name
            if not self.repo_owner:
                # Try to extract from common patterns
                if "team-" in repo_name:
                    self.repo_owner = ""
            
            # Check what needs fixing
            needs_fixing = self._check_csvs_need_fixing(repo_dir)
            
            if not needs_fixing["needs_fix"]:
                print(f"[INFO] ✓ All CSVs look good, skipping")
                summary["repo_details"].append({
                    "name": repo_name,
                    "status": "skipped",
                    "files_fixed": 0
                })
                continue
            
            print(f"[INFO] Issues found in {len(needs_fixing['files_to_fix'])} file(s)")
            for issue in needs_fixing['issues'][:5]:  # Show first 5
                print(f"  - {issue}")
            
            # Reset cache for new repo
            self.commit_cache.clear()
            self.pr_cache.clear()
            self.cache_hits = 0
            self.cache_misses = 0
            
            # Fix the CSVs
            try:
                fixed_files = []
                
                for csv_file in repo_dir.glob("*.csv"):
                    if '_fixed' in csv_file.stem:
                        continue
                    
                    if 'commit' in csv_file.stem.lower() and 'file_changes' not in csv_file.stem.lower():
                        fixed = self.fix_commits_csv_optimized(str(csv_file))
                        fixed_files.append(fixed)
                    elif 'pull_request' in csv_file.stem.lower():
                        fixed = self.fix_pr_csv_optimized(str(csv_file))
                        fixed_files.append(fixed)
                
                summary["total_files_fixed"] += len(fixed_files)
                summary["repos_fixed"] += 1
                
                summary["repo_details"].append({
                    "name": repo_name,
                    "status": "fixed",
                    "files_fixed": len(fixed_files)
                })
                
                print(f"[INFO] ✓ Fixed {len(fixed_files)} file(s)")
                
            except Exception as e:
                print(f"[ERROR] Failed: {e}")
                summary["repo_details"].append({
                    "name": repo_name,
                    "status": "error",
                    "error": str(e)
                })
        
        # Final summary
        elapsed = time.time() - summary["start_time"]
        
        print("\n" + "="*80)
        print("FIXING SUMMARY")
        print("="*80)
        print(f"Repositories scanned: {summary['repos_scanned']}")
        print(f"Repositories fixed:   {summary['repos_fixed']}")
        print(f"Total files fixed:    {summary['total_files_fixed']}")
        print(f"Time elapsed:         {elapsed:.1f}s")
        print(f"Cache efficiency:     {self.cache_hits}/{self.cache_hits+self.cache_misses} hits")
        print("="*80)
        
        return summary
    
    def _check_csvs_need_fixing(self, repo_dir: Path) -> Dict:
        """Quick check if CSVs need fixing."""
        csv_files = [f for f in repo_dir.glob("*.csv") if '_fixed' not in f.stem]
        
        if not csv_files:
            return {"needs_fix": False, "files_to_fix": [], "issues": []}
        
        issues = []
        files_to_fix = []
        
        for csv_file in csv_files:
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    fieldnames = reader.fieldnames or []
                    
                    # Sample first 10 rows
                    rows = [row for i, row in enumerate(reader) if i < 10]
                    
                    if not rows:
                        continue
                    
                    file_issues = []
                    
                    # Check commits CSV
                    if 'commit' in csv_file.stem.lower() and 'file_changes' not in csv_file.stem.lower():
                        missing_dates = sum(1 for row in rows if not row.get('commit_date', '').strip())
                        missing_paths = sum(1 for row in rows if not row.get('file_path', '').strip())
                        
                        if missing_dates > len(rows) * 0.5:
                            file_issues.append(f"Missing dates: {missing_dates}/{len(rows)}")
                        if missing_paths > len(rows) * 0.5:
                            file_issues.append(f"Missing paths: {missing_paths}/{len(rows)}")
                    
                    # Check PR CSV
                    elif 'pull_request' in csv_file.stem.lower():
                        if 'is_up_to_date' not in fieldnames:
                            file_issues.append("Missing 'is_up_to_date'")
                        if 'has_conflicts' not in fieldnames:
                            file_issues.append("Missing 'has_conflicts'")
                    
                    if file_issues:
                        files_to_fix.append(csv_file.name)
                        issues.extend([f"{csv_file.name}: {issue}" for issue in file_issues])
            
            except Exception:
                continue
        
        return {
            "needs_fix": len(files_to_fix) > 0,
            "files_to_fix": files_to_fix,
            "issues": issues
        }


# Example usage
if __name__ == "__main__":
    import sys
    
    fixer = OptimizedCSVFixer(github_token=None)
    
    # Determine directory
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
    else:
        possible_dirs = ["./data/csv", "../data/csv", "../../data/csv", "./csv", "../csv"]
        base_dir = None
        for dir_path in possible_dirs:
            if Path(dir_path).exists():
                base_dir = dir_path
                print(f"[INFO] Found data directory: {base_dir}")
                break
        
        if not base_dir:
            print("\n[ERROR] Could not find data/csv directory!")
            print("\nUsage: python csvFix.py /path/to/data/csv")
            print("\nSearched in:")
            for dir_path in possible_dirs:
                print(f"  - {Path(dir_path).resolve()}")
            sys.exit(1)
    
    print("\n=== OPTIMIZED AUTO-FIX ===")
    print("Features:")
    print("  ✓ Batch processing (50 commits at a time)")
    print("  ✓ Parallel API calls (10 workers)")
    print("  ✓ Intelligent caching")
    print("  ✓ Progress tracking")
    print("="*80)
    
    summary = fixer.scan_and_fix_all_repos(base_dir)
    
    print("\n=== RESULTS ===")
    if summary.get('total_files_fixed', 0) > 0:
        print("✓ CSVs fixed successfully!")
        print("  - Original files preserved")
        print("  - Fixed files have '_fixed' suffix")
    else:
        print("ℹ No fixes needed - all CSVs are correct!")