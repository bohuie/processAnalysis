"""
Pull Request Extractor with Branch Support and Orphan Commit Detection
Includes smart log filtering that only matches "log/logs" as standalone words
"""

import os
import csv
import json
import time
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor  # ADD THIS IMPORT

import requests
from dateutil import parser
from dotenv import load_dotenv
from tqdm import tqdm

# Import handling with fallbacks for debugging
try:
    from src.models.pull_request_file import PullRequestFile
    from src.models.user import User
    from src.models.pull_request import PullRequest
    from src.models.commit import Commit
    from src.extractors.git_extractor import GitExtractor
    from src.utils.file_config import JSONFileConfiguration
    from src.utils.filename import construct_file_name
    from src.utils.file_path import get_project_data_csv_folder, get_project_data_json_folder
    from src.utils.github_url import (
        get_github_all_changed_files_of_pr_id_url,
        get_github_commits_of_pr_id_html_url,
        get_github_pull_request_url_by_id,
        get_github_commits_of_pr_id_url,
    )
    from src.utils.request_counter import RequestCounter
    print("[DEBUG] All imports successful")
except ImportError as e:
    print(f"[DEBUG] Import error: {e}")
    # Define fallback classes to prevent crashes
    class PullRequestFile:
        def __init__(self, data): 
            self.data = data
            self.filename = data.get('filename') if isinstance(data, dict) else getattr(data, 'filename', '')
            self.additions = data.get('additions', 0) if isinstance(data, dict) else getattr(data, 'additions', 0)
            self.deletions = data.get('deletions', 0) if isinstance(data, dict) else getattr(data, 'deletions', 0)
    
    class User:
        def __init__(self, data): 
            self.data = data
            self.login = data.get('login') if isinstance(data, dict) else getattr(data, 'login', 'Unknown')
            self.username = data.get('username') if isinstance(data, dict) else getattr(data, 'username', 'Unknown')
    
    class PullRequest:
        def __init__(self, data, commits=None, files=None, review_authors=None, comments=None, url_html=None):
            self._raw_data = data
            self.commits = commits or []
            self.all_changed_files = files or []
            self.review_authors = review_authors or []
            self.comments = comments or []
            self.url_html = url_html
            # Extract common fields
            if isinstance(data, dict):
                self.pr_id = data.get('number')
                self.id = data.get('number')
                self.pr_title = data.get('title', '')
                self.state = data.get('state', '')
                self.created_at = data.get('created_at', '')
                self.updated_at = data.get('updated_at', '')
                self.closed_at = data.get('closed_at', '')
                self.merged_at = data.get('merged_at', '')
                self.merged_by = data.get('merged_by')
                self.user = User(data.get('user', {}))
                self.head = data.get('head', {})
                self.base = data.get('base', {})
                self.merge_commit_sha = data.get('merge_commit_sha')
                self.mergeable_state = data.get('mergeable_state', '')
                self.pr_description = data.get('body', '')
            else:
                self.pr_id = getattr(data, 'pr_id', getattr(data, 'id', None))
                self.id = getattr(data, 'id', None)
                self.pr_title = getattr(data, 'pr_title', '')
                self.state = getattr(data, 'state', '')
                self.created_at = getattr(data, 'created_at', '')
                self.updated_at = getattr(data, 'updated_at', '')
                self.closed_at = getattr(data, 'closed_at', '')
                self.merged_at = getattr(data, 'merged_at', '')
                self.merged_by = getattr(data, 'merged_by', None)
                self.user = getattr(data, 'user', User({}))
                self.head = getattr(data, 'head', {})
                self.base = getattr(data, 'base', {})
                self.merge_commit_sha = getattr(data, 'merge_commit_sha', '')
                self.mergeable_state = getattr(data, 'mergeable_state', '')
                self.pr_description = getattr(data, 'pr_description', '')
        
        def todict(self):
            return self._raw_data if hasattr(self, '_raw_data') else {}
    
    class Commit:
        def __init__(self, data):
            self._raw_data = data
            if isinstance(data, dict):
                self.sha = data.get('sha')
                self.message = data.get('commit', {}).get('message', '') if 'commit' in data else data.get('message', '')
                self.author = User(data.get('author', {}))
                self.date = data.get('commit', {}).get('author', {}).get('date') if 'commit' in data else data.get('date', '')
                self.files = data.get('files', [])
            else:
                self.sha = getattr(data, 'sha', '')
                self.message = getattr(data, 'message', '')
                self.author = getattr(data, 'author', User({}))
                self.date = getattr(data, 'date', '')
                self.files = getattr(data, 'files', [])
        
        def todict(self):
            return self._raw_data
    
    class GitExtractor:
        def __init__(self, repo_owner, repo_name, need_auth=True, request_counter=None):
            self.repo_owner = repo_owner
            self.repo_name = repo_name
            self.need_auth = need_auth
            self.request_counter = request_counter
            self.header = None
    
    class JSONFileConfiguration:
        def __init__(self):
            self.indent = 2
    
    def construct_file_name(owner, repo, file_type, identifier):
        return f"{owner}_{repo}_{file_type}_{identifier}"
    
    def get_project_data_csv_folder():
        return "./data/csv"
    
    def get_project_data_json_folder():
        return "./data/json"
    
    def get_github_all_changed_files_of_pr_id_url(owner, repo, pr_id, per_page=100):
        return f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_id}/files?per_page={per_page}"
    
    def get_github_commits_of_pr_id_html_url(owner, repo, pr_id):
        return f"https://github.com/{owner}/{repo}/pull/{pr_id}/commits"
    
    def get_github_pull_request_url_by_id(owner, repo, pr_id):
        return f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_id}"
    
    def get_github_commits_of_pr_id_url(owner, repo, pr_id):
        return f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_id}/commits"
    
    class RequestCounter:
        def __init__(self):
            self.count = 0
        def increment(self):
            self.count += 1


class LogFilterMixin:
    """Log filtering - only matches 'log/logs' as standalone words."""
    
    LOG_PATTERN = re.compile(r'(?<![a-zA-Z])(logs?)(?![a-zA-Z])', re.IGNORECASE)
    LOG_PATH_KEYWORDS = ['/logs/', '/log/', '_logs/', '_log/', 'logs/', 'log/']
    
    @classmethod
    def is_log_pr(cls, pr_title: Optional[str] = None, pr_body: Optional[str] = None) -> bool:
        print(f"[DEBUG] Checking if PR is log-related: title='{pr_title[:50] if pr_title else None}'")
        if pr_title and cls.LOG_PATTERN.search(pr_title):
            print("[DEBUG] PR title contains log pattern")
            return True
        if pr_body and cls.LOG_PATTERN.search(pr_body[:200]):
            print("[DEBUG] PR body contains log pattern")
            return True
        return False
    
    @classmethod
    def is_log_file(cls, filename: Optional[str]) -> bool:
        if not filename:
            return False
        filename_lower = filename.lower()
        if any(kw in filename_lower for kw in cls.LOG_PATH_KEYWORDS):
            print(f"[DEBUG] File '{filename}' is in log directory")
            return True
        result = bool(cls.LOG_PATTERN.search(os.path.basename(filename_lower)))
        if result:
            print(f"[DEBUG] File '{filename}' matches log pattern")
        return result
    
    @classmethod
    def is_log_commit(cls, commit_message: Optional[str]) -> bool:
        if not commit_message:
            return False
        result = bool(cls.LOG_PATTERN.search(commit_message.split('\n')[0]))
        if result:
            print(f"[DEBUG] Commit message contains log pattern: {commit_message[:50]}")
        return result
    
    @classmethod
    def is_log_comment(cls, comment_body: Optional[str]) -> bool:
        if not comment_body:
            return False
        result = bool(cls.LOG_PATTERN.search(comment_body[:100]))
        if result:
            print(f"[DEBUG] Comment contains log pattern: {comment_body[:50]}")
        return result


class PullRequestExtractor(GitExtractor, LogFilterMixin):
    """Extracts pull request data from GitHub repositories."""

    DEFAULT_RESULTS_PER_PAGE = 100
    RATE_LIMIT_BUFFER_SECONDS = 5
    REQUEST_TIMEOUT_SECONDS = 30
    RETRY_WAIT_TIME = 60
    MAX_RETRIES = 5
    MAX_PAGES = 50  # ADD SAFETY LIMIT
    
    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        need_auth: bool = True,
        request_counter: RequestCounter = None,
        exclude_readme: bool = False,
        exclude_logs: bool = True,
    ):
        print(f"[DEBUG] Initializing PullRequestExtractor for {repo_owner}/{repo_name}")
        super().__init__(repo_owner, repo_name, need_auth, request_counter)
        self.exclude_readme = exclude_readme
        self.exclude_logs = exclude_logs
        self._setup_authentication()
        
        self.stats = {
            'prs_filtered': 0,
            'commits_filtered': 0,
            'files_filtered': 0,
            'comments_filtered': 0,
        }
        
        self.csv_filepath = None
        self.commit_csv_filepath = None
        self.commit_file_changes_csv_filepath = None
        self.review_comments_csv_filepath = None

    def _setup_authentication(self):
        """Load GitHub authentication token."""
        print("[DEBUG] Setting up authentication")
        self.headers = getattr(self, "header", None)
        
        if self.headers is None:
            load_dotenv()
            token = os.getenv("GITHUB_TOKEN")
            if not token:
                print("[ERROR] No GITHUB_TOKEN found in .env file!")
            else:
                print("[DEBUG] GITHUB_TOKEN found and loaded")
            self.headers = {"Authorization": f"token {token}"} if token else {}
        print(f"[DEBUG] Headers configured: {'Yes' if self.headers else 'No'}")

    def print_filtering_stats(self):
        """Print filtering statistics."""
        if not self.exclude_logs:
            return
        print(f"\n{'='*60}")
        print("LOG FILTERING STATISTICS")
        print(f"{'='*60}")
        print(f"PRs filtered:      {self.stats['prs_filtered']}")
        print(f"Commits filtered:  {self.stats['commits_filtered']}")
        print(f"Files filtered:    {self.stats['files_filtered']}")
        print(f"Comments filtered: {self.stats['comments_filtered']}")
        print(f"{'='*60}\n")

    @staticmethod
    def is_readme_file(filename: Optional[str]) -> bool:
        if not filename:
            return False
        result = os.path.basename(filename).lower().startswith("readme")
        if result:
            print(f"[DEBUG] File '{filename}' is a README")
        return result

    def should_exclude_file(self, filename: Optional[str], pr_title: Optional[str] = None) -> bool:
        if not filename:
            return False
        if self.exclude_logs and self.is_log_file(filename):
            self.stats['files_filtered'] += 1
            return True
        if self.exclude_readme and pr_title and self.is_log_pr(pr_title):
            if self.is_readme_file(filename):
                self.stats['files_filtered'] += 1
                return True
        return False

    def filter_files(self, files: List[PullRequestFile], pr_title: Optional[str] = None) -> List[PullRequestFile]:
        filtered = [f for f in files if not self.should_exclude_file(getattr(f, "filename", ""), pr_title)]
        print(f"[DEBUG] Filtered {len(files) - len(filtered)} files")
        return filtered

    def check_rate_limit(self) -> Tuple[Optional[int], Optional[float]]:
        try:
            print("[DEBUG] Checking rate limit...")
            response = requests.get("https://api.github.com/rate_limit", headers=self.headers, timeout=10)
            if response.status_code == 200:
                core = response.json().get("resources", {}).get("core", {})
                remaining = core.get("remaining")
                reset = core.get("reset")
                print(f"[DEBUG] Rate limit: {remaining} remaining, reset at {reset}")
                return remaining, reset
            else:
                print(f"[DEBUG] Rate limit check failed: {response.status_code}")
        except Exception as e:
            print(f"[DEBUG] Rate limit check error: {e}")
        return None, None

    def wait_for_rate_limit_reset(self, reset_time: float):
        if reset_time:
            wait = float(reset_time) - time.time() + self.RATE_LIMIT_BUFFER_SECONDS
            if wait > 0:
                print(f"[INFO] Rate limit exceeded. Waiting {int(wait)} seconds...")
                time.sleep(wait)

    def make_request_with_backoff(self, url: str, max_retries: int = None, wait_time: int = None, backoff_factor: float = 2.0) -> Optional[requests.Response]:
        max_retries = max_retries or self.MAX_RETRIES
        wait_time = wait_time or self.RETRY_WAIT_TIME
        delay = wait_time
        
        print(f"[DEBUG] Making request to: {url}")
        
        for attempt in range(1, max_retries + 1):
            try:
                remaining, reset_time = self.check_rate_limit()
                if remaining is not None and remaining < 10:
                    self.wait_for_rate_limit_reset(reset_time)
                
                response = requests.get(url, headers=self.headers, timeout=self.REQUEST_TIMEOUT_SECONDS)
                if self.request_counter:
                    self.request_counter.increment()
                
                print(f"[DEBUG] Request attempt {attempt}: Status {response.status_code}")
                
                if response.status_code == 200:
                    return response
                
                if response.status_code == 403:
                    print(f"[DEBUG] 403 Forbidden on attempt {attempt}")
                    remaining, reset_time = self.check_rate_limit()
                    if remaining == 0:
                        self.wait_for_rate_limit_reset(reset_time)
                    else:
                        print(f"[DEBUG] Waiting {delay} seconds before retry")
                        time.sleep(delay)
                    delay *= backoff_factor
                    continue
                
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                print(f"[DEBUG] Request exception on attempt {attempt}: {e}")
                if attempt < max_retries:
                    print(f"[DEBUG] Waiting {delay} seconds before retry")
                    time.sleep(delay)
                    delay *= backoff_factor
                    continue
                break
            except Exception as e:
                print(f"[DEBUG] Unexpected error on attempt {attempt}: {e}")
                if attempt < max_retries:
                    print(f"[DEBUG] Waiting {delay} seconds before retry")
                    time.sleep(delay)
                    delay *= backoff_factor
                    continue
                break
        
        print(f"[ERROR] Failed after {max_retries} attempts: {url}")
        return None

    def _fetch_commit_files(self, commit_sha: str) -> List[Dict]:
        print(f"[DEBUG] Fetching files for commit {commit_sha[:8]}...")
        response = self.make_request_with_backoff(
            f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/{commit_sha}"
        )
        if response:
            files = response.json().get("files", [])
            print(f"[DEBUG] Found {len(files)} files for commit {commit_sha[:8]}")
            return files
        return []

    def _fetch_commit_details(self, commit_sha: str) -> Dict:
        print(f"[DEBUG] Fetching details for commit {commit_sha[:8]}...")
        response = self.make_request_with_backoff(
            f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/{commit_sha}"
        )
        return response.json() if response else {}

    def extract_commits_from_pull_request(
        self,
        pr_id: int,
        blacklisted_users: Optional[List[str]] = None,
        save_data_to_json: bool = False,
        json_config: JSONFileConfiguration = JSONFileConfiguration(),
    ) -> List[Commit]:
        print(f"[DEBUG] Extracting commits from PR #{pr_id}")
        url = get_github_commits_of_pr_id_url(self.repo_owner, self.repo_name, pr_id)
        response = self.make_request_with_backoff(url)
        if not response:
            print(f"[DEBUG] No response for PR #{pr_id} commits")
            return []

        data = response.json() or []
        print(f"[DEBUG] Found {len(data)} commits in PR #{pr_id}")
        blacklisted_users = blacklisted_users or []
        commits = []
        
        for commit in data:
            if commit.get("author") and commit["author"].get("login") in blacklisted_users:
                print(f"[DEBUG] Skipping blacklisted user commit")
                continue
            commit_message = commit.get("commit", {}).get("message", "")
            if self.exclude_logs and self.is_log_commit(commit_message):
                self.stats['commits_filtered'] += 1
                print(f"[DEBUG] Filtered log-related commit: {commit_message[:50]}")
                continue
            commits.append(Commit({**commit, "description": "Commit"}))

        print(f"[DEBUG] Returning {len(commits)} commits after filtering")
        if save_data_to_json:
            self._save_commits_to_json(commits, pr_id, json_config)
        return commits

    def _save_commits_to_json(self, commits: List[Commit], pr_id: int, json_config: JSONFileConfiguration):
        filename = construct_file_name(self.repo_owner, self.repo_name, "commits", pr_id)
        output_dir = Path(get_project_data_json_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump([c.todict() for c in commits], f, indent=json_config.indent)
        print(f"[DEBUG] Saved {len(commits)} commits to JSON")

    def extract_pull_request_file_changes(self, pr_id: int, results_per_page: int = None) -> List[Dict]:
        results_per_page = results_per_page or self.DEFAULT_RESULTS_PER_PAGE
        url = get_github_all_changed_files_of_pr_id_url(self.repo_owner, self.repo_name, pr_id, results_per_page)
        print(f"[DEBUG] Extracting file changes for PR #{pr_id}")
        response = self.make_request_with_backoff(url)
        if not response:
            return []

        all_files = response.json() or []
        print(f"[DEBUG] Initial file changes: {len(all_files)} files")
        
        # Handle pagination safely
        page_count = 1
        while getattr(response, "links", None) and "next" in response.links and page_count < self.MAX_PAGES:
            next_url = response.links["next"]["url"]
            print(f"[DEBUG] Fetching next page of files: {page_count}")
            response = self.make_request_with_backoff(next_url)
            if response:
                new_files = response.json() or []
                all_files.extend(new_files)
                print(f"[DEBUG] Added {len(new_files)} files from page {page_count}")
                page_count += 1
            else:
                break
        
        print(f"[DEBUG] Total file changes: {len(all_files)} files")
        return all_files

    def extract_pull_request_by_id(self, pr_id: int, blacklisted_users: Optional[List[str]] = None, save_data_to_json: bool = True) -> Optional[PullRequest]:
        print(f"[DEBUG] ========== EXTRACTING PR #{pr_id} ==========")
        blacklisted_users = blacklisted_users or []
        url = get_github_pull_request_url_by_id(self.repo_owner, self.repo_name, pr_id)
        url_html = get_github_commits_of_pr_id_html_url(self.repo_owner, self.repo_name, pr_id)

        response = self.make_request_with_backoff(url)
        if not response:
            print(f"[DEBUG] Failed to fetch PR #{pr_id}")
            return None

        pr_data = response.json()
        print(f"[DEBUG] PR #{pr_id} data retrieved successfully")
        pr_data["description"] = "PR Description"

        
        pr_title = pr_data.get("title") # Removed default to check for None
        pr_body = pr_data.get("body")   # Removed default to check for None
        # Safely treat pr_title and pr_body as empty strings if they are None
        pr_title_safe = pr_title or ""
        pr_body_safe = pr_body or ""
        
        if self.exclude_logs and self.is_log_pr(pr_title_safe, pr_body_safe):
            self.stats['prs_filtered'] += 1
            print(f"[DEBUG] PR #{pr_id} filtered due to log content: Title='{pr_title_safe[:50]}' Body='{pr_body_safe[:50]}'")
            return None

        if pr_data.get("user", {}).get("login") in blacklisted_users:
            print(f"[DEBUG] PR #{pr_id} filtered due to blacklisted user")
            return None

        print(f"[DEBUG] Extracting commits for PR #{pr_id}")
        commits = self.extract_commits_from_pull_request(pr_id, blacklisted_users=blacklisted_users, save_data_to_json=False)
        print(f"[DEBUG] Extracting file changes for PR #{pr_id}")
        file_changes = self.extract_pull_request_file_changes(pr_id)
        all_changed_files = [PullRequestFile(f) for f in file_changes]

        print(f"[DEBUG] Extracting review comments for PR #{pr_id}")
        # FIX: Use the correct method name - _extract_review_comments instead of _extract_review_comments_enhanced
        review_authors, comments = self._extract_review_comments(pr_id, pr_data, blacklisted_users)
        
        # DEBUG: Print what we found
        print(f"[DEBUG] PR #{pr_id} - Review authors found: {len(review_authors)}")
        for i, author in enumerate(review_authors):
            login = getattr(author, 'login', getattr(author, 'username', 'Unknown'))
            print(f"[DEBUG]   Author {i+1}: {login}")

        # Ensure all fields are populated with default values if missing
        merged_by = pr_data.get('merged_by', {}).get('login') if pr_data.get('merged_by') else 'Unknown'
        merged_at = pr_data.get('merged_at', '')
        merge_commit_sha = pr_data.get('merge_commit_sha', '')

        pull_request = PullRequest(pr_data, commits, all_changed_files, review_authors, comments=comments, url_html=url_html)
        pull_request._raw_data = pr_data

        if pr_data.get("merged") and merge_commit_sha:
            print(f"[DEBUG] Checking merge status for PR #{pr_id}")
            merge_status = self.get_merge_sync_status_from_api(
                base_sha=pr_data.get("base", {}).get("sha"),
                merge_commit_sha=merge_commit_sha,
                pr_id=pr_id
            )
            pull_request.was_up_to_date_at_merge = merge_status.get("was_up_to_date_at_merge")
            pull_request.was_behind_at_merge = merge_status.get("was_behind_at_merge")
        else:
            pull_request.was_up_to_date_at_merge = None
            pull_request.was_behind_at_merge = None

        if save_data_to_json:
            self._save_pr_to_json(pull_request, pr_id)

        print(f"[DEBUG] ========== COMPLETED PR #{pr_id} ==========")
        return pull_request

    def _fetch_review_comments_directly(self, pr_id: int) -> Tuple[List[Dict], List[User]]:
        """Fallback method to fetch review comments directly from GitHub API"""
        print(f"[DEBUG] Fetching review comments directly for PR #{pr_id}")
        comments = []
        review_authors = []
        
        # Fetch review comments
        review_comments_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/comments"
        response = self.make_request_with_backoff(review_comments_url)
        
        if response and response.status_code == 200:
            review_comments_data = response.json() or []
            print(f"[DEBUG] Found {len(review_comments_data)} review comments via direct API")
            
            for comment_data in review_comments_data:
                # Extract author information
                author_data = comment_data.get('user', {})
                if author_data:
                    author = User(author_data)
                    review_authors.append(author)
                    
                    comments.append({
                        "id": comment_data.get('id'),
                        "body": comment_data.get('body', ''),
                        "user": author_data,
                        "author": author_data.get('login', 'Unknown'),
                        "created_at": comment_data.get('created_at'),
                        "updated_at": comment_data.get('updated_at'),
                        "comment_body": comment_data.get('body', ''),
                        "user_login": author_data.get('login', 'Unknown'),
                    })
        
        # Also fetch issue comments (regular PR comments)
        issue_comments_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_id}/comments"
        response = self.make_request_with_backoff(issue_comments_url)
        
        if response and response.status_code == 200:
            issue_comments_data = response.json() or []
            print(f"[DEBUG] Found {len(issue_comments_data)} issue comments via direct API")
            
            for comment_data in issue_comments_data:
                author_data = comment_data.get('user', {})
                if author_data:
                    author = User(author_data)
                    review_authors.append(author)
                    
                    comments.append({
                        "id": comment_data.get('id'),
                        "body": comment_data.get('body', ''),
                        "user": author_data,
                        "author": author_data.get('login', 'Unknown'),
                        "created_at": comment_data.get('created_at'),
                        "updated_at": comment_data.get('updated_at'),
                        "comment_body": comment_data.get('body', ''),
                        "user_login": author_data.get('login', 'Unknown'),
                    })
        
        # Remove duplicates from review_authors
        unique_authors = []
        seen_logins = set()
        for author in review_authors:
            login = getattr(author, 'login', getattr(author, 'username', 'Unknown'))
            if login not in seen_logins:
                seen_logins.add(login)
                unique_authors.append(author)
        
        print(f"[DEBUG] Direct fetch: {len(comments)} comments, {len(unique_authors)} unique authors")
        return unique_authors, comments

    def _extract_review_comments(self, pr_id: int, pr_data: Dict, blacklisted_users: List[str]) -> Tuple[List[User], List[Dict]]:
        print(f"[DEBUG] Extracting review comments for PR #{pr_id}")
        review_authors = []
        comments = []
        try:
            # Try to import CommentExtractor, but provide fallback if it fails
            try:
                from src.extractors.comment_extractor import CommentExtractor
                extractor = CommentExtractor(self.repo_owner, self.repo_name, self.headers, self.request_counter)
                review_comments = extractor.extract_review_comments_for_repo_with_id(
                    pr_id=pr_id,
                    pr_author=User(pr_data.get("user")),
                    save_data_to_json=False,
                    save_data_to_csv=False,
                    blacklisted_users=blacklisted_users,
                )
            except ImportError:
                print(f"[DEBUG] CommentExtractor not available, using empty comments")
                review_comments = []

            # FIX: Add proper fallback when CommentExtractor fails
            if not review_comments:
                # Try direct API call as fallback
                review_authors, comments = self._fetch_review_comments_directly(pr_id)
                return review_authors, comments
            
            for comment in review_comments:
                comment_dict = comment.todict()
                if self.exclude_logs and self.is_log_comment(comment_dict.get("comment_body", "")):
                    self.stats['comments_filtered'] += 1
                    continue
                comment_dict["description"] = "PR Comment"
                comments.append(comment_dict)

            review_authors = list({cmt.author.username: cmt.author for cmt in review_comments}.values())
            print(f"[DEBUG] Found {len(comments)} comments and {len(review_authors)} review authors")
        except Exception as e:
            print(f"[WARN] Comment extraction failed for PR #{pr_id}: {e}")
            # FIX: Add fallback extraction
            review_authors, comments = self._fetch_review_comments_directly(pr_id)
        return review_authors, comments

    def _save_pr_to_json(self, pull_request: PullRequest, pr_id: int):
        filename = construct_file_name(self.repo_owner, self.repo_name, "PR", str(pr_id))
        output_dir = Path(get_project_data_json_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump(pull_request.todict(), f, indent=2)
        print(f"[DEBUG] Saved PR #{pr_id} to JSON")

    def calculate_metrics(self, all_changed_files: List[PullRequestFile], pr_title: Optional[str] = None) -> Dict:
        print(f"[DEBUG] Calculating metrics for PR")
        files_to_count = self.filter_files(all_changed_files, pr_title)
        lines_added = sum(getattr(f, "additions", 0) for f in files_to_count)
        lines_deleted = sum(getattr(f, "deletions", 0) for f in files_to_count)
        files_changed = len(files_to_count)

        top_file = None
        top_file_pct = None
        
        if files_to_count:
            file_changes = {}
            for file_obj in files_to_count:
                filename = getattr(file_obj, "filename", None)
                if filename:
                    additions = getattr(file_obj, "additions", 0)
                    deletions = getattr(file_obj, "deletions", 0)
                    file_changes[filename] = file_changes.get(filename, 0) + additions + deletions
            
            if file_changes:
                total_changes = sum(file_changes.values())
                if total_changes > 0:
                    top_file = max(file_changes, key=file_changes.get)
                    top_file_pct = round((file_changes[top_file] / total_changes) * 100, 2)

        metrics = {
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "files_changed": files_changed,
            "top_file": top_file,
            "top_file_pct": top_file_pct,
        }
        print(f"[DEBUG] Metrics calculated: {metrics}")
        return metrics

    def get_merge_sync_status_from_api(self, base_sha: str, merge_commit_sha: str, pr_id: Optional[int] = None) -> Dict:
        print(f"[DEBUG] Getting merge sync status for PR #{pr_id}")
        result = {"was_up_to_date_at_merge": None, "was_behind_at_merge": None}
        if not base_sha or not merge_commit_sha:
            print(f"[DEBUG] Missing SHA for merge status check")
            return result

        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/compare/{base_sha}...{merge_commit_sha}"
        response = self.make_request_with_backoff(url)
        
        if response and response.status_code == 200:
            behind_by = response.json().get("behind_by")
            result["was_behind_at_merge"] = behind_by
            result["was_up_to_date_at_merge"] = (behind_by == 0) if behind_by is not None else None
            print(f"[DEBUG] Merge status: behind_by={behind_by}, up_to_date={result['was_up_to_date_at_merge']}")
        else:
            print(f"[DEBUG] Failed to get merge status: {response.status_code if response else 'No response'}")
        return result

    def find_orphan_commits(self, branch: str = "main") -> List[Dict]:
        print(f"[INFO] Scanning '{branch}' for orphan commits...")
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits"
        all_commits = []
        page = 1
        
        while True:
            print(f"[DEBUG] Fetching orphan commits page {page}")
            response = self.make_request_with_backoff(f"{url}?sha={branch}&per_page=100&page={page}")
            if not response:
                print(f"[DEBUG] No response for orphan commits page {page}")
                break
            data = response.json() or []
            if not data:
                print(f"[DEBUG] No more orphan commits on page {page}")
                break
            all_commits.extend(data)
            print(f"[DEBUG] Added {len(data)} commits from page {page}, total: {len(all_commits)}")
            page += 1
            if page > self.MAX_PAGES:  # ADD SAFETY LIMIT
                print(f"[WARN] Reached maximum page limit ({self.MAX_PAGES}), stopping")
                break
            if page % 5 == 0:
                print(f"[PROGRESS] Fetched {len(all_commits)} commits...")
        
        print(f"[INFO] Found {len(all_commits)} commits on '{branch}'")
        return all_commits

    def extract_pull_requests_with_pagination(
        self,
        pull_request_status: str = "all",
        result_per_page: int = None,
        save_data_to_json: bool = False,
        save_data_to_csv: bool = True,
        csv_filename: Optional[str] = None,
        include_orphan_commits: bool = True,
        branch_for_orphans: str = "master",
    ) -> List[PullRequest]:
        print(f"[INFO] ========== STARTING PR EXTRACTION ==========")
        result_per_page = result_per_page or self.DEFAULT_RESULTS_PER_PAGE
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls?state={pull_request_status}&per_page={result_per_page}"
        
        all_pull_requests = []
        page = 1

        while True:
            print(f"[INFO] Fetching page {page} of pull requests...")
            response = self.make_request_with_backoff(f"{url}&page={page}")
            if not response:
                print(f"[DEBUG] No response for PR page {page}, stopping")
                break
            data = response.json() or []
            if not data:
                print(f"[DEBUG] No more PRs on page {page}, stopping")
                break
            
            print(f"[DEBUG] Processing {len(data)} PRs on page {page}")
            for pr_data in data:
                pr = self.extract_pull_request_by_id(pr_data["number"], save_data_to_json=False)
                if pr:
                    all_pull_requests.append(pr)
                    print(f"[DEBUG] Added PR #{pr_data['number']} to results")
                else:
                    print(f"[DEBUG] PR #{pr_data['number']} was filtered out")
            page += 1
            if page > self.MAX_PAGES:  # ADD SAFETY LIMIT
                print(f"[WARN] Reached maximum page limit ({self.MAX_PAGES}), stopping")
                break
            print(f"[DEBUG] Completed page {page-1}, total PRs so far: {len(all_pull_requests)}")

        print(f"[INFO] Extracted {len(all_pull_requests)} pull requests")

        if save_data_to_json:
            print(f"[DEBUG] Saving PRs to JSON")
            self.save_pull_requests_to_json(all_pull_requests)

        if save_data_to_csv:
            csv_filename = csv_filename or f"{self.repo_name}_all_pull_requests"
            print(f"[DEBUG] Saving data to CSV files")
            self.save_pull_requests_to_csv(all_pull_requests, csv_filename)
            self.save_commits_to_csv(all_pull_requests, f"{self.repo_name}_PR_commits", include_orphan_commits, branch_for_orphans)
            self.save_commit_file_changes_to_csv(all_pull_requests, f"{self.repo_name}_commit_file_changes", include_orphan_commits, branch_for_orphans)
            self.save_review_comments_to_csv(all_pull_requests, f"{self.repo_name}_review-comments")
        
        self.print_filtering_stats()
        print(f"[INFO] ========== COMPLETED PR EXTRACTION ==========")
        return all_pull_requests

    def save_pull_requests_to_json(self, pull_requests: List[PullRequest]):
        filename = f"{self.repo_owner}_{self.repo_name}_all_pull_requests"
        output_dir = Path(get_project_data_json_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / f"{filename}.json", "w", encoding="utf-8") as f:
            json.dump([pr.todict() for pr in pull_requests], f, indent=2)
        print(f"[INFO] ✓ Pull requests saved to: {output_dir / filename}.json")

    def _get_branch_name(self, pr, branch_type: str) -> str:
        try:
            branch_obj = getattr(pr, branch_type, None)
            if branch_obj:
                if hasattr(branch_obj, 'ref'):
                    return branch_obj.ref
                elif isinstance(branch_obj, dict):
                    return branch_obj.get('ref', 'Unknown')
            if hasattr(pr, '_raw_data') and branch_type in pr._raw_data:
                return pr._raw_data[branch_type].get('ref', 'Unknown')
            return "Unknown"
        except Exception as e:
            print(f"[DEBUG] Error getting {branch_type} branch: {e}")
            return "Unknown"

    def _get_pr_author(self, pr) -> str:
        try:
            user_obj = getattr(pr, "user", None)
            if user_obj:
                if hasattr(user_obj, 'login'):
                    return user_obj.login
                elif hasattr(user_obj, 'username'):
                    return user_obj.username
                elif isinstance(user_obj, dict):
                    return user_obj.get('login', user_obj.get('username', 'Unknown'))
            if hasattr(pr, '_raw_data') and 'user' in pr._raw_data and pr._raw_data['user']:
                return pr._raw_data['user'].get('login', 'Unknown')
            return "Unknown"
        except Exception as e:
            print(f"[DEBUG] Error getting PR author: {e}")
            return "Unknown"

    def _get_reviewers(self, pr) -> List[str]:
        """Enhanced reviewers extraction with multiple fallbacks"""
        try:
            # Method 1: Try review_authors attribute
            review_authors = getattr(pr, "review_authors", [])
            reviewers = []
            
            if review_authors:
                for user in review_authors:
                    if hasattr(user, 'login'):
                        reviewers.append(user.login)
                    elif hasattr(user, 'username'):
                        reviewers.append(user.username)
                    elif isinstance(user, dict):
                        reviewers.append(user.get('login', user.get('username', 'Unknown')))
                    else:
                        reviewers.append(str(user))
            
            # Method 2: If no reviewers found, try to extract from PR data
            if not reviewers and hasattr(pr, '_raw_data'):
                pr_data = pr._raw_data
                # Try to get requested reviewers
                requested_reviewers = pr_data.get('requested_reviewers', [])
                for reviewer in requested_reviewers:
                    if isinstance(reviewer, dict) and 'login' in reviewer:
                        reviewers.append(reviewer['login'])
                
                # Try to get assignees
                assignees = pr_data.get('assignees', [])
                for assignee in assignees:
                    if isinstance(assignee, dict) and 'login' in assignee:
                        reviewers.append(assignee['login'])
            
            # Method 3: Extract from comments if available
            if not reviewers and hasattr(pr, 'comments'):
                comment_authors = set()
                for comment in getattr(pr, 'comments', []):
                    author = comment.get('author') or comment.get('user_login')
                    if author and author != 'Unknown':
                        comment_authors.add(author)
                reviewers.extend(list(comment_authors))
            
            # Remove duplicates and PR author
            pr_author = self._get_pr_author(pr)
            unique_reviewers = [r for r in set(reviewers) if r != pr_author and r != 'Unknown']
            
            print(f"[DEBUG] Found {len(unique_reviewers)} reviewers: {unique_reviewers}")
            return unique_reviewers
            
        except Exception as e:
            print(f"[DEBUG] Error getting reviewers: {e}")
            return []

    def _get_merge_info(self, pr) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            merged_by, merged_at, merge_commit_sha = None, None, None
            if hasattr(pr, "_raw_data"):
                merged_by_data = pr._raw_data.get("merged_by")
                if merged_by_data:
                    merged_by = merged_by_data.get("login")
                    merged_at = pr._raw_data.get("merged_at")
                    merge_commit_sha = pr._raw_data.get("merge_commit_sha")
            return merged_by, merged_at, merge_commit_sha
        except Exception as e:
            print(f"[DEBUG] Error getting merge info: {e}")
            return None, None, None

    def save_pull_requests_to_csv(self, pull_requests: List[PullRequest], csv_filename: str, repo_clone_path: str = "./cloned_repos"):
        output_dir = Path(get_project_data_csv_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{csv_filename}.csv"
        self.csv_filepath = csv_path

        print(f"[INFO] Writing PR data to {csv_path}")

        fieldnames = [
            "Action", "pr_id", "pr_title", "pr_author", "head_branch", "base_branch",
            "state", "created_at", "updated_at", "closed_at", "merged_at", "merged_by",
            "num_commits", "num_reviewers", "reviewers", "pr_description",
            "mergeable_state", "is_up_to_date", "was_up_to_date_at_merge",
            "has_conflicts", "is_self_merged", "line_added", "line_deleted",
            "total_changes", "files_changed", "was_behind_at_merge", "top_file",
            "top_file_change_%", "docs_updated", "has_readme_changes",
            "feature_documentation_status", "description",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for pr in pull_requests:
                try:
                    head_branch = self._get_branch_name(pr, "head")
                    base_branch = self._get_branch_name(pr, "base")
                    reviewers_list = self._get_reviewers(pr)
                    pr_author = self._get_pr_author(pr)
                    merged_by, merged_at, merge_commit_sha = self._get_merge_info(pr)
                    metrics = self.calculate_metrics(getattr(pr, "all_changed_files", []), getattr(pr, "pr_title", ""))

                    writer.writerow({
                        "Action": "PR Description",
                        "pr_id": getattr(pr, "pr_id", getattr(pr, "id", None)),
                        "pr_title": getattr(pr, "pr_title", ""),
                        "pr_author": pr_author,
                        "head_branch": head_branch,
                        "base_branch": base_branch,
                        "state": getattr(pr, "state", ""),
                        "created_at": getattr(pr, "created_at", ""),
                        "updated_at": getattr(pr, "updated_at", ""),
                        "closed_at": getattr(pr, "closed_at", ""),
                        "merged_at": merged_at,
                        "merged_by": merged_by,
                        "num_commits": len(getattr(pr, "commits", [])),
                        "num_reviewers": len(reviewers_list),
                        "reviewers": ", ".join(reviewers_list),
                        "pr_description": getattr(pr, "pr_description", ""),
                        "mergeable_state": getattr(pr, "mergeable_state", ""),
                        "is_up_to_date": getattr(pr, "is_up_to_date", False),
                        "was_up_to_date_at_merge": getattr(pr, "was_up_to_date_at_merge", False),
                        "has_conflicts": getattr(pr, "has_conflicts", False),
                        "is_self_merged": getattr(pr, "is_self_merged", False),
                        "line_added": metrics["lines_added"],
                        "line_deleted": metrics["lines_deleted"],
                        "total_changes": metrics["lines_added"] + metrics["lines_deleted"],
                        "files_changed": metrics["files_changed"],
                        "was_behind_at_merge": getattr(pr, "was_behind_at_merge", 0),
                        "top_file": metrics["top_file"],
                        "top_file_change_%": metrics["top_file_pct"],
                        "docs_updated": getattr(pr, "docs_updated", False),
                        "has_readme_changes": getattr(pr, "has_readme_changes", False),
                        "feature_documentation_status": getattr(pr, "feature_documentation_status", None),
                        "description": "PR Description",
                    })
                except Exception as e:
                    print(f"[ERROR] Failed PR #{getattr(pr, 'pr_id', 'Unknown')}: {e}")
        
        print(f"[INFO] ✓ {len(pull_requests)} PRs saved to: {csv_path}")

    def save_commits_to_csv(self, pull_requests: List[PullRequest], csv_filename: str, include_orphans: bool = False, branch: str = "main"):
        output_dir = Path(get_project_data_csv_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{csv_filename}.csv"
        self.commit_csv_filepath = csv_path

        print(f"[INFO] Writing commits to {csv_path}")

        fieldnames = [
            "repo_name", "pr_id", "pr_author", "head_branch", "base_branch",
            "commit_sha", "author", "commit_date", "file_path", "lines_added",
            "lines_deleted", "commit_message", "message_word_count",
        ]

        all_rows = []
        pr_commit_shas = set()

        for pr in pull_requests:
            pr_id = getattr(pr, "pr_id", getattr(pr, "id", None))
            pr_author = self._get_pr_author(pr)
            head_branch = self._get_branch_name(pr, "head")
            base_branch = self._get_branch_name(pr, "base")

            for commit in getattr(pr, "commits", []):
                commit_sha = getattr(commit, "sha", None)
                if commit_sha:
                    pr_commit_shas.add(commit_sha)
                
                commit_message = getattr(commit, "message", "")
                if self.exclude_logs and self.is_log_commit(commit_message):
                    continue

                # FIX: Properly extract commit author and date
                commit_author = "Unknown"
                commit_date = None
                
                # Try multiple ways to get author
                author_obj = getattr(commit, "author", None)
                if author_obj:
                    if hasattr(author_obj, 'login'):
                        commit_author = author_obj.login
                    elif hasattr(author_obj, 'username'):
                        commit_author = author_obj.username
                    elif isinstance(author_obj, dict):
                        commit_author = author_obj.get('login', author_obj.get('username', 'Unknown'))
                
                # Try multiple ways to get date
                commit_date = getattr(commit, "date", None)
                if commit_date is None and hasattr(commit, "_raw_data"):
                    commit_data = commit._raw_data
                    # Try commit.author.date from raw data
                    if 'commit' in commit_data and 'author' in commit_data['commit']:
                        commit_date = commit_data['commit']['author'].get('date')
                    elif 'author' in commit_data and commit_data['author']:
                        commit_date = commit_data['author'].get('date')
                
                files = getattr(commit, "files", [])
                if not files:
                    all_rows.append({
                        "repo_name": self.repo_name, 
                        "pr_id": pr_id, 
                        "pr_author": pr_author,
                        "head_branch": head_branch, 
                        "base_branch": base_branch, 
                        "commit_sha": commit_sha,
                        "author": commit_author,  # FIXED: Use extracted author
                        "commit_date": commit_date,  # FIXED: Use extracted date
                        "file_path": "",
                        "lines_added": 0, 
                        "lines_deleted": 0,
                        "commit_message": commit_message.split('\n')[0],
                        "message_word_count": len(commit_message.split()),
                    })
                else:
                    for file_data in files:
                        file_name = getattr(file_data, "filename", getattr(file_data, "name", ""))
                        if self.exclude_logs and self.is_log_file(file_name):
                            continue
                        
                        # FIX: Properly extract file changes
                        lines_added = getattr(file_data, "additions", 0)
                        lines_deleted = getattr(file_data, "deletions", 0)
                        
                        all_rows.append({
                            "repo_name": self.repo_name, 
                            "pr_id": pr_id, 
                            "pr_author": pr_author,
                            "head_branch": head_branch, 
                            "base_branch": base_branch, 
                            "commit_sha": commit_sha,
                            "author": commit_author,  # FIXED: Use extracted author
                            "commit_date": commit_date,  # FIXED: Use extracted date
                            "file_path": file_name,
                            "lines_added": lines_added,  # FIXED: Use extracted additions
                            "lines_deleted": lines_deleted,  # FIXED: Use extracted deletions
                            "commit_message": commit_message.split('\n')[0],
                            "message_word_count": len(commit_message.split()),
                        })

        if include_orphans:
            print(f"[INFO] Finding orphan commits on '{branch}'...")
            all_branch_commits = self.find_orphan_commits(branch)
            orphan_count = 0

            for commit_data in tqdm(all_branch_commits, desc="Processing orphans"):
                commit_sha = commit_data.get("sha")
                if commit_sha in pr_commit_shas:
                    continue
                
                orphan_count += 1
                if orphan_count > 1000:
                    print(f"[DEBUG] Stopping orphan processing at 1000 commits")
                    break

                commit_info = commit_data.get("commit", {})
                commit_message = commit_info.get("message", "")
                if self.exclude_logs and self.is_log_commit(commit_message):
                    continue

                # FIX: Properly extract author and date for orphan commits
                author_info = commit_data.get("author") or {}
                commit_author = author_info.get("login", "Unknown")
                
                # Get commit date from commit info
                author_details = commit_info.get("author", {})
                commit_date_str = author_details.get("date")
                commit_timestamp = None
                if commit_date_str:
                    try:
                        commit_timestamp = parser.parse(commit_date_str).timestamp()
                    except:
                        commit_timestamp = commit_date_str

                commit_files = self._fetch_commit_files(commit_sha)
                if not commit_files:
                    all_rows.append({
                        "repo_name": self.repo_name, 
                        "pr_id": None, 
                        "pr_author": None,
                        "head_branch": branch, 
                        "base_branch": None, 
                        "commit_sha": commit_sha,
                        "author": commit_author,  # FIXED
                        "commit_date": commit_timestamp,  # FIXED
                        "file_path": "", 
                        "lines_added": 0, 
                        "lines_deleted": 0,
                        "commit_message": commit_message.split('\n')[0],
                        "message_word_count": len(commit_message.split()),
                    })
                else:
                    for file_info in commit_files:
                        file_name = file_info.get("filename", "")
                        if self.exclude_logs and self.is_log_file(file_name):
                            continue
                        
                        # FIX: Extract file changes properly
                        lines_added = file_info.get("additions", 0)
                        lines_deleted = file_info.get("deletions", 0)
                        
                        all_rows.append({
                            "repo_name": self.repo_name, 
                            "pr_id": None, 
                            "pr_author": None,
                            "head_branch": branch, 
                            "base_branch": None, 
                            "commit_sha": commit_sha,
                            "author": commit_author,  # FIXED
                            "commit_date": commit_timestamp,  # FIXED
                            "file_path": file_name, 
                            "lines_added": lines_added,  # FIXED
                            "lines_deleted": lines_deleted,  # FIXED
                            "commit_message": commit_message.split('\n')[0],
                            "message_word_count": len(commit_message.split()),
                        })
            print(f"[INFO] Found {orphan_count} orphan commits")

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"[INFO] ✓ {len(all_rows)} commit rows saved to: {csv_path}")
    
    def save_commit_file_changes_to_csv(self, pull_requests: List[PullRequest], csv_filename: str, include_orphans: bool = False, branch: str = "main"):
        output_dir = Path(get_project_data_csv_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{csv_filename}.csv"
        self.commit_file_changes_csv_filepath = csv_path

        print(f"[INFO] Writing file changes to {csv_path}")

        fieldnames = [
            "repo_name", "pr_id", "pr_author", "head_branch", "base_branch",
            "commit_sha", "commit_author", "commit_date", "commit_message",
            "file_path", "file_status", "lines_added", "lines_deleted",
            "total_changes", "previous_filename",
        ]

        all_rows = []
        pr_commit_shas = set()

        for pr in tqdm(pull_requests, desc="Processing PRs"):
            pr_id = getattr(pr, "pr_id", getattr(pr, "id", None))
            pr_author = self._get_pr_author(pr)
            head_branch = self._get_branch_name(pr, "head")
            base_branch = self._get_branch_name(pr, "base")

            for commit in getattr(pr, "commits", []):
                commit_sha = getattr(commit, "sha", None)
                if commit_sha:
                    pr_commit_shas.add(commit_sha)

                commit_message = getattr(commit, "message", "")
                if self.exclude_logs and self.is_log_commit(commit_message):
                    continue

                files = getattr(commit, "files", [])
                if not files and commit_sha:
                    files = self._fetch_commit_files(commit_sha)

                if not files:
                    all_rows.append({
                        "repo_name": self.repo_name, "pr_id": pr_id, "pr_author": pr_author,
                        "head_branch": head_branch, "base_branch": base_branch, "commit_sha": commit_sha,
                        "commit_author": getattr(getattr(commit, "author", None), "login", "Unknown"),
                        "commit_date": getattr(commit, "date", None),
                        "commit_message": commit_message.split('\n')[0][:100],
                        "file_path": "", "file_status": "no_changes", "lines_added": 0,
                        "lines_deleted": 0, "total_changes": 0, "previous_filename": "",
                    })
                else:
                    for file_data in files:
                        if isinstance(file_data, dict):
                            file_name = file_data.get("filename", "")
                            lines_added = file_data.get("additions", 0)
                            lines_deleted = file_data.get("deletions", 0)
                            file_status = file_data.get("status", "modified")
                            previous_filename = file_data.get("previous_filename", "")
                        else:
                            file_name = getattr(file_data, "filename", getattr(file_data, "name", ""))
                            lines_added = getattr(file_data, "additions", 0)
                            lines_deleted = getattr(file_data, "deletions", 0)
                            file_status = getattr(file_data, "status", "modified")
                            previous_filename = getattr(file_data, "previous_filename", "")

                        if self.exclude_logs and self.is_log_file(file_name):
                            continue

                        all_rows.append({
                            "repo_name": self.repo_name, "pr_id": pr_id, "pr_author": pr_author,
                            "head_branch": head_branch, "base_branch": base_branch, "commit_sha": commit_sha,
                            "commit_author": getattr(getattr(commit, "author", None), "login", "Unknown"),
                            "commit_date": getattr(commit, "date", None),
                            "commit_message": commit_message.split('\n')[0][:100],
                            "file_path": file_name, "file_status": file_status,
                            "lines_added": lines_added, "lines_deleted": lines_deleted,
                            "total_changes": lines_added + lines_deleted,
                            "previous_filename": previous_filename,
                        })

        if include_orphans:
            print(f"[INFO] Finding orphan commits on '{branch}'...")
            all_branch_commits = self.find_orphan_commits(branch)
            orphan_count = 0

            for commit_data in tqdm(all_branch_commits, desc="Processing orphans"):
                commit_sha = commit_data.get("sha")
                if commit_sha in pr_commit_shas:
                    continue

                orphan_count += 1
                if orphan_count > 1000:
                    print(f"[DEBUG] Stopping orphan processing at 1000 commits")
                    break

                commit_info = commit_data.get("commit", {})
                commit_message = commit_info.get("message", "")
                if self.exclude_logs and self.is_log_commit(commit_message):
                    continue

                author_info = commit_data.get("author") or {}
                commit_date_str = commit_info.get("author", {}).get("date")
                commit_timestamp = None
                if commit_date_str:
                    try:
                        commit_timestamp = parser.parse(commit_date_str).timestamp()
                    except:
                        commit_timestamp = commit_date_str

                commit_files = self._fetch_commit_files(commit_sha)
                if not commit_files:
                    all_rows.append({
                        "repo_name": self.repo_name, "pr_id": None, "pr_author": None,
                        "head_branch": branch, "base_branch": None, "commit_sha": commit_sha,
                        "commit_author": author_info.get("login", "Unknown"),
                        "commit_date": commit_timestamp,
                        "commit_message": commit_message.split('\n')[0][:100],
                        "file_path": "", "file_status": "no_changes", "lines_added": 0,
                        "lines_deleted": 0, "total_changes": 0, "previous_filename": "",
                    })
                else:
                    for file_info in commit_files:
                        file_name = file_info.get("filename", "")
                        if self.exclude_logs and self.is_log_file(file_name):
                            continue
                        all_rows.append({
                            "repo_name": self.repo_name, "pr_id": None, "pr_author": None,
                            "head_branch": branch, "base_branch": None, "commit_sha": commit_sha,
                            "commit_author": author_info.get("login", "Unknown"),
                            "commit_date": commit_timestamp,
                            "commit_message": commit_message.split('\n')[0][:100],
                            "file_path": file_name, "file_status": file_info.get("status", "modified"),
                            "lines_added": file_info.get("additions", 0),
                            "lines_deleted": file_info.get("deletions", 0),
                            "total_changes": file_info.get("additions", 0) + file_info.get("deletions", 0),
                            "previous_filename": file_info.get("previous_filename", ""),
                        })
            print(f"[INFO] Found {orphan_count} orphan commits")

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"[INFO] ✓ {len(all_rows)} file change rows saved to: {csv_path}")

    def save_review_comments_to_csv(self, pull_requests: List[PullRequest], csv_filename: str):
        output_dir = Path(get_project_data_csv_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{csv_filename}.csv"
        self.review_comments_csv_filepath = csv_path

        print(f"[INFO] Writing review comments to {csv_path}")

        fieldnames = [
            "pr_id", "comment_id", "pr_author", "author", "comment_body",
            "comment_word_count", "created_at", "updated_at", "user_login",
            "state", "order_of_review"
        ]

        all_rows = []

        for pr in pull_requests:
            pr_id = getattr(pr, "pr_id", getattr(pr, "id", None))
            pr_author = self._get_pr_author(pr)

            for comment_dict in getattr(pr, "comments", []):
                comment_body = comment_dict.get("comment_body", "")
                if self.exclude_logs and self.is_log_comment(comment_body):
                    continue

                all_rows.append({
                    "pr_id": pr_id,
                    "comment_id": comment_dict.get("id"),
                    "pr_author": pr_author,
                    "author": comment_dict.get("author", "Unknown"),
                    "comment_body": comment_body,
                    "comment_word_count": len(comment_body.split()),
                    "created_at": comment_dict.get("created_at"),
                    "updated_at": comment_dict.get("updated_at"),
                    "user_login": comment_dict.get("user_login"),
                    "state": comment_dict.get("state"),
                    "order_of_review": comment_dict.get("order_of_review"),
                })

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"[INFO] ✓ {len(all_rows)} review comments saved to: {csv_path}")

    # ==================== BRANCH EXTRACTION (NO PR REQUIRED) ====================
    
    def extract_all_branches(self) -> List[Dict]:
        """Extract all branches from the repository."""
        print(f"[INFO] Fetching all branches for {self.repo_owner}/{self.repo_name}...")
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/branches"
        all_branches = []
        page = 1
        
        while True:
            print(f"[DEBUG] Fetching branches page {page}")
            response = self.make_request_with_backoff(f"{url}?per_page=100&page={page}")
            if not response:
                break
            data = response.json() or []
            if not data:
                break
            all_branches.extend(data)
            page += 1
            if page > self.MAX_PAGES:  # ADD SAFETY LIMIT
                print(f"[WARN] Reached maximum page limit ({self.MAX_PAGES}), stopping")
                break
            if page % 5 == 0:
                print(f"[PROGRESS] Fetched {len(all_branches)} branches...")
        
        print(f"[INFO] Found {len(all_branches)} total branches")
        return all_branches

    def extract_commits_from_branch(
        self, 
        branch_name: str = "main",
        since: Optional[str] = None,
        until: Optional[str] = None,
        max_commits: Optional[int] = None,
        identify_orphans: bool = False
    ) -> List[Dict]:
        """
        Extract commits from a specific branch without requiring PR IDs.
        
        Args:
            branch_name: Branch to extract from (default: 'main')
            since: ISO 8601 date string - only commits after this date
            until: ISO 8601 date string - only commits before this date
            max_commits: Maximum number of commits to fetch
            identify_orphans: If True, mark which commits are orphans (not in any PR)
        
        Returns:
            List of commit dictionaries with optional 'is_orphan' field
        """
        print(f"[INFO] Fetching commits from branch '{branch_name}'...")
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits"
        all_commits = []
        page = 1
        
        while True:
            params = f"?sha={branch_name}&per_page=100&page={page}"
            if since:
                params += f"&since={since}"
            if until:
                params += f"&until={until}"
            
            print(f"[DEBUG] Fetching commits page {page} from branch '{branch_name}'")
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            for commit_data in data:
                commit_message = commit_data.get("commit", {}).get("message", "")
                if self.exclude_logs and self.is_log_commit(commit_message):
                    self.stats['commits_filtered'] += 1
                    continue
                all_commits.append(commit_data)
            
            page += 1
            if max_commits and len(all_commits) >= max_commits:
                all_commits = all_commits[:max_commits]
                break
            if page > self.MAX_PAGES:  # ADD SAFETY LIMIT
                print(f"[WARN] Reached maximum page limit ({self.MAX_PAGES}), stopping")
                break
            if page % 5 == 0:
                print(f"[PROGRESS] Fetched {len(all_commits)} commits from '{branch_name}'...")
        
        print(f"[INFO] Found {len(all_commits)} commits on branch '{branch_name}'")
        
        if identify_orphans:
            all_commits = self._mark_orphan_commits(all_commits, branch_name)
        
        return all_commits

    def _mark_orphan_commits(self, commits: List[Dict], branch_name: str) -> List[Dict]:
        """Identify which commits are orphans (not associated with any PR)."""
        print(f"[INFO] Identifying orphan commits...")
        pr_commit_shas = self._get_all_pr_commit_shas()
        
        orphan_count = 0
        for commit in commits:
            commit_sha = commit.get("sha")
            if commit_sha in pr_commit_shas:
                commit["is_orphan"] = False
                commit["pr_id"] = pr_commit_shas[commit_sha]
            else:
                commit["is_orphan"] = True
                commit["pr_id"] = None
                orphan_count += 1
        
        print(f"[INFO] Found {orphan_count} orphan commits out of {len(commits)} total")
        return commits

    def _get_all_pr_commit_shas(self) -> Dict[str, int]:
        """Fetch all PR commit SHAs. Returns dict mapping commit_sha -> pr_id."""
        print(f"[INFO] Fetching all PRs to identify orphan commits...")
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls"
        pr_commits = {}
        page = 1
        
        while True:
            response = self.make_request_with_backoff(f"{url}?state=all&per_page=100&page={page}")
            if not response:
                break
            
            prs = response.json() or []
            if not prs:
                break
            
            for pr in prs:
                pr_id = pr.get("number")
                commits_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/commits"
                commits_response = self.make_request_with_backoff(commits_url)
                
                if commits_response:
                    commits = commits_response.json() or []
                    for commit in commits:
                        commit_sha = commit.get("sha")
                        if commit_sha:
                            pr_commits[commit_sha] = pr_id
            
            page += 1
            if page > self.MAX_PAGES:  # ADD SAFETY LIMIT
                print(f"[WARN] Reached maximum page limit ({self.MAX_PAGES}), stopping")
                break
            if page % 5 == 0:
                print(f"[PROGRESS] Processed {len(pr_commits)} PR commits...")
        
        print(f"[INFO] Found {len(pr_commits)} commits associated with PRs")
        return pr_commits

    def extract_orphan_commits_only(
        self,
        branch_name: str = "main",
        since: Optional[str] = None,
        until: Optional[str] = None,
        max_commits: Optional[int] = None
    ) -> List[Dict]:
        """Extract ONLY orphan commits (commits not in any PR) from a branch."""
        all_commits = self.extract_commits_from_branch(
            branch_name=branch_name,
            since=since,
            until=until,
            max_commits=max_commits,
            identify_orphans=True
        )
        
        orphan_commits = [c for c in all_commits if c.get("is_orphan", False)]
        print(f"[INFO] Filtered to {len(orphan_commits)} orphan commits")
        return orphan_commits

    def save_branch_commits_to_csv(
        self,
        branch_name: str = "main",
        csv_filename: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        max_commits: Optional[int] = None,
        orphans_only: bool = False
    ):
        """
        Extract and save commits from a branch to CSV (no PR required).
        
        Args:
            branch_name: Branch to extract from
            csv_filename: Output filename (auto-generated if None)
            since: ISO 8601 date - only commits after this date
            until: ISO 8601 date - only commits before this date
            max_commits: Maximum commits to fetch
            orphans_only: If True, only save orphan commits (not in any PR)
        """
        print(f"[INFO] Starting branch commit extraction for '{branch_name}'")
        if orphans_only:
            commits = self.extract_orphan_commits_only(branch_name, since, until, max_commits)
        else:
            commits = self.extract_commits_from_branch(branch_name, since, until, max_commits, identify_orphans=True)
        
        if not commits:
            print("[WARN] No commits found to save")
            return
        
        output_dir = Path(get_project_data_csv_folder()) / self.repo_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        suffix = "_orphans" if orphans_only else ""
        csv_filename = csv_filename or f"{self.repo_name}_branch_{branch_name.replace('/', '_')}_commits{suffix}"
        csv_path = output_dir / f"{csv_filename}.csv"
        
        print(f"[INFO] Writing branch commits to {csv_path}")
        
        fieldnames = [
            "repo_name", "branch_name", "commit_sha", "author", "author_email",
            "commit_date", "commit_message", "message_word_count", "files_changed",
            "additions", "deletions", "total_changes", "is_orphan", "pr_id",
        ]
        
        all_rows = []
        for commit_data in tqdm(commits, desc=f"Processing '{branch_name}' commits"):
            commit_sha = commit_data.get("sha")
            author_info = commit_data.get("author") or {}
            commit_info = commit_data.get("commit", {})
            author_details = commit_info.get("author", {})
            commit_message = commit_info.get("message", "")
            commit_date = author_details.get("date")
            
            commit_timestamp = None
            if commit_date:
                try:
                    commit_timestamp = parser.parse(commit_date).timestamp()
                except:
                    commit_timestamp = commit_date
            
            commit_details = self._fetch_commit_details(commit_sha)
            stats = commit_details.get("stats", {})
            
            all_rows.append({
                "repo_name": self.repo_name,
                "branch_name": branch_name,
                "commit_sha": commit_sha,
                "author": author_info.get("login", "Unknown"),
                "author_email": author_details.get("email", ""),
                "commit_date": commit_timestamp,
                "commit_message": commit_message.split('\n')[0][:200],
                "message_word_count": len(commit_message.split()),
                "files_changed": len(commit_details.get("files", [])),
                "additions": stats.get("additions", 0),
                "deletions": stats.get("deletions", 0),
                "total_changes": stats.get("total", 0),
                "is_orphan": commit_data.get("is_orphan", False),
                "pr_id": commit_data.get("pr_id"),
            })
        
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        
        orphan_count = sum(1 for row in all_rows if row["is_orphan"])
        print(f"[INFO] ✓ Saved {len(all_rows)} commits to: {csv_path}")
        print(f"[INFO]   → {orphan_count} orphan commits, {len(all_rows) - orphan_count} PR commits")


# Example usage and test function
if __name__ == "__main__":
    print("=== Testing PullRequestExtractor ===")
    
    # Initialize extractor
    extractor = PullRequestExtractor(
        repo_owner="microsoft",  # Use a public repo for testing
        repo_name="vscode",
        need_auth=False,  # Set to True if you have GITHUB_TOKEN
        exclude_logs=True
    )
    
    # Test basic functionality
    print("\n1. Testing branch extraction...")
    branches = extractor.extract_all_branches()
    print(f"Found {len(branches)} branches")
    
    print("\n2. Testing commit extraction from main branch...")
    commits = extractor.extract_commits_from_branch("main", max_commits=10)
    print(f"Found {len(commits)} commits")
    
    print("\n3. Testing PR extraction (limited)...")
    prs = extractor.extract_pull_requests_with_pagination(
        pull_request_status="closed",
        result_per_page=5,  # Small number for testing
        save_data_to_csv=False,  # Don't save during test
        save_data_to_json=False,
        include_orphan_commits=False
    )
    print(f"Found {len(prs)} pull requests")
    
    print("\n=== Test completed ===")