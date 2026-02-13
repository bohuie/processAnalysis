import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

# Eextracts full file contents
import base64
from urllib.parse import quote

# Import handling with fallbacks for development
try:
    from src.extractors.git_extractor import GitExtractor
    from src.utils.request_counter import RequestCounter
    print("[DEBUG] Imports successful")
except ImportError as e:
    print(f"[DEBUG] Import error (using fallbacks): {e}")
    
    class GitExtractor:
        """Fallback base class"""
        def __init__(self, repo_owner, repo_name, need_auth=True, request_counter=None):
            self.repo_owner = repo_owner
            self.repo_name = repo_name
            self.need_auth = need_auth
            self.request_counter = request_counter
    
    class RequestCounter:
        """Fallback request counter"""
        def __init__(self):
            self.count = 0
        def increment(self):
            self.count += 1


class PullRequestExtractor(GitExtractor):
    """
    Pure data extractor for GitHub Pull Requests.
    
    Responsibilities:
    - API communication
    - Rate limit management
    - Pagination handling
    - Raw data retrieval
    
    Not Responsible For:
    - Data filtering
    - Data transformation
    - Metrics calculation
    - File I/O (CSV/JSON)
    - Business logic
    """

    # API Configuration
    DEFAULT_RESULTS_PER_PAGE = 100
    RATE_LIMIT_BUFFER_SECONDS = 5
    REQUEST_TIMEOUT_SECONDS = 30
    RETRY_WAIT_TIME = 60
    MAX_RETRIES = 5
    MAX_PAGES = 50  # Safety limit for pagination
    
    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        need_auth: bool = True,
        request_counter: RequestCounter = None,
    ):
        """
        Initialize the pure data extractor.
        
        Args:
            repo_owner: GitHub repository owner (e.g., "microsoft")
            repo_name: GitHub repository name (e.g., "vscode")
            need_auth: Whether to use GitHub token authentication
            request_counter: Optional counter for tracking API requests
        """
        print(f"[INFO] Initializing PullRequestExtractor for {repo_owner}/{repo_name}")
        super().__init__(repo_owner, repo_name, need_auth, request_counter)
        self._setup_authentication()

    # ============================================================================
    # AUTHENTICATION
    # ============================================================================

    def _setup_authentication(self):
        """
        Load GitHub authentication token from environment.
        Expects GITHUB_TOKEN in .env file or environment variables.
        """
        print("[DEBUG] Setting up authentication")
        self.headers = getattr(self, "header", None)
        
        if self.headers is None:
            load_dotenv()
            token = os.getenv("GITHUB_TOKEN")
            if not token:
                print("[WARN] No GITHUB_TOKEN found - API rate limits will be restricted")
            else:
                print("[DEBUG] GITHUB_TOKEN loaded successfully")
            self.headers = {"Authorization": f"token {token}"} if token else {}
        
        # Initialize request session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    # ============================================================================
    # RATE LIMITING
    # ============================================================================

    def check_rate_limit(self) -> Tuple[Optional[int], Optional[float]]:
        """
        Check current GitHub API rate limit status.
        
        Returns:
            Tuple of (remaining_requests, reset_timestamp)
            Returns (None, None) if check fails
        """
        try:
            response = requests.get(
                "https://api.github.com/rate_limit", 
                headers=self.headers, 
                timeout=10
            )
            if response.status_code == 200:
                core = response.json().get("resources", {}).get("core", {})
                remaining = core.get("remaining")
                reset = core.get("reset")
                return remaining, reset
        except Exception as e:
            print(f"[WARN] Rate limit check failed: {e}")
        return None, None

    def wait_for_rate_limit_reset(self, reset_time: float):
        """
        Block until rate limit resets.
        
        Args:
            reset_time: Unix timestamp when rate limit resets
        """
        if reset_time:
            wait = float(reset_time) - time.time() + self.RATE_LIMIT_BUFFER_SECONDS
            if wait > 0:
                print(f"[INFO] Rate limit exceeded. Waiting {int(wait)} seconds...")
                time.sleep(wait)

    def get_api_rate_limit_info(self) -> Dict:
        """
        Get detailed rate limit information for all resource types.
        
        Returns:
            Dictionary containing rate limit details:
            - resources.core: Core API rate limit
            - resources.search: Search API rate limit
            - resources.graphql: GraphQL API rate limit
        """
        try:
            response = requests.get(
                "https://api.github.com/rate_limit",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[ERROR] Failed to get rate limit info: {e}")
        return {}

    # ============================================================================
    # HTTP REQUEST HANDLING
    # ============================================================================

    def make_request_with_backoff(
        self, 
        url: str, 
        max_retries: int = None, 
        wait_time: int = None, 
        backoff_factor: float = 2.0
    ) -> Optional[requests.Response]:
        """
        Make HTTP request with exponential backoff retry logic.
        
        Features:
        - Automatic rate limit detection and waiting
        - Exponential backoff on failures
        - Request counting for statistics
        - Comprehensive error handling
        
        Args:
            url: Full API endpoint URL
            max_retries: Maximum retry attempts (default: 5)
            wait_time: Initial wait time in seconds (default: 60)
            backoff_factor: Multiplier for wait time on each retry (default: 2.0)
            
        Returns:
            requests.Response object if successful
            None if all retries exhausted
        """
        max_retries = max_retries or self.MAX_RETRIES
        wait_time = wait_time or self.RETRY_WAIT_TIME
        delay = wait_time
        
        for attempt in range(1, max_retries + 1):
            try:
                # Pre-flight rate limit check
                remaining, reset_time = self.check_rate_limit()
                if remaining is not None and remaining < 10:
                    print(f"[INFO] Low rate limit ({remaining}), waiting...")
                    self.wait_for_rate_limit_reset(reset_time)
                
                # Make request
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    timeout=self.REQUEST_TIMEOUT_SECONDS
                )
                
                # Track request count
                if self.request_counter:
                    self.request_counter.increment()
                
                # Success
                if response.status_code == 200:
                    return response
                
                # Rate limit hit
                if response.status_code == 403:
                    remaining, reset_time = self.check_rate_limit()
                    if remaining == 0:
                        self.wait_for_rate_limit_reset(reset_time)
                    else:
                        time.sleep(delay)
                    delay *= backoff_factor
                    continue
                
                # Other errors
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                print(f"[WARN] Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff_factor
                    continue
                break
            except Exception as e:
                print(f"[ERROR] Unexpected error (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= backoff_factor
                    continue
                break
        
        print(f"[ERROR] All retries exhausted for: {url}")
        return None

    # ============================================================================
    # PULL REQUEST EXTRACTION
    # ============================================================================

    def extract_pull_request_by_id(self, pr_id: int) -> Optional[Dict]:
        """
        Extract raw data for a single pull request.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            Dictionary containing raw PR data from GitHub API:
            - number, title, state, created_at, updated_at, closed_at, merged_at
            - user (author), merged_by, head, base, merge_commit_sha
            - body (description), mergeable_state, labels, assignees
            - review_comments, comments, commits (counts)
            
        Note: This does NOT include commits, files, or comments.
              Use separate methods to fetch those.
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return None
        
        data = response.json()
        if data.get("merged_by"):
            data["merged_by_login"] = data["merged_by"].get("login")
        else:
            data["merged_by_login"] = None

        return data


    def extract_all_pull_requests(
        self,
        state: str = "all",
        per_page: int = None,
        max_pages: int = None,
        sort: str = "created",
        direction: str = "desc"
    ) -> List[Dict]:
        """
        Extract all pull requests with pagination.
        
        Args:
            state: Filter by state ("open", "closed", "all")
            per_page: Results per page (default: 100, max: 100)
            max_pages: Maximum pages to fetch (default: 50)
            sort: Sort field ("created", "updated", "popularity", "long-running")
            direction: Sort direction ("asc", "desc")
            
        Returns:
            List of raw PR data dictionaries
            
        Note: This only returns PR summaries, not full details.
              Use extract_pull_request_by_id() for complete data.
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls"
        all_prs = []
        page = 1

        print(f"[INFO] Extracting PRs (state={state}, sort={sort}, direction={direction})...")
        
        while page <= max_pages:
            params = f"?state={state}&per_page={per_page}&page={page}&sort={sort}&direction={direction}"
            
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            all_prs.extend(data)
            print(f"[PROGRESS] Page {page}: +{len(data)} PRs (total: {len(all_prs)})")
            page += 1

        print(f"[INFO] Extracted {len(all_prs)} pull requests")
        return all_prs

    # ============================================================================
    # COMMIT EXTRACTION
    # ============================================================================

    def extract_commits_from_pr(self, pr_id: int) -> List[Dict]:
        """
        Extract all commits for a specific pull request.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            List of commit data dictionaries:
            - sha, author, committer, message, date
            - parents, tree
            - Does NOT include file changes (use extract_commit_details)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/commits"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return []

        commits = response.json() or []
        return commits

    def extract_commit_details(self, commit_sha: str) -> Dict:
        """
        Extract detailed information for a specific commit.
        
        Args:
            commit_sha: Commit SHA hash
            
        Returns:
            Dictionary containing:
            - All fields from extract_commits_from_pr()
            - Plus: files (list of changed files with stats)
            - stats (total additions, deletions, changes)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits/{commit_sha}"
        
        response = self.make_request_with_backoff(url)
        return response.json() if response else {}

    def extract_commits_from_branch(
        self, 
        branch_name: str = "main",
        since: Optional[str] = None,
        until: Optional[str] = None,
        per_page: int = None,
        max_pages: int = None,
        author: Optional[str] = None
    ) -> List[Dict]:
        """
        Extract commits from a specific branch.
        
        Args:
            branch_name: Branch name to extract from
            since: ISO 8601 date - only commits after this date
            until: ISO 8601 date - only commits before this date
            per_page: Results per page (default: 100)
            max_pages: Maximum pages to fetch (default: 50)
            author: Filter by commit author (GitHub username or email)
            
        Returns:
            List of commit data dictionaries (same format as extract_commits_from_pr)
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/commits"
        all_commits = []
        page = 1
        
        print(f"[INFO] Extracting commits from branch '{branch_name}'...")
        
        while page <= max_pages:
            params = f"?sha={branch_name}&per_page={per_page}&page={page}"
            if since:
                params += f"&since={since}"
            if until:
                params += f"&until={until}"
            if author:
                params += f"&author={author}"
            
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            all_commits.extend(data)
            print(f"[PROGRESS] Page {page}: +{len(data)} commits (total: {len(all_commits)})")
            page += 1
        
        print(f"[INFO] Extracted {len(all_commits)} commits from '{branch_name}'")
        return all_commits

    # ============================================================================
    # FILE CHANGES EXTRACTION
    # ============================================================================

    def extract_pr_file_changes(
        self, 
        pr_id: int, 
        per_page: int = None,
        max_pages: int = None,
    ) -> List[Dict]:
        """
        Extract all file changes for a pull request.
        
        Args:
            pr_id: Pull request number
            per_page: Results per page (default: 100)
            max_pages: Maximum pages to fetch (default: 50)
            
        Returns:
            List of file change dictionaries:
            - filename, status (added/modified/removed/renamed)
            - additions, deletions, changes
            - patch (diff content)
            - previous_filename (for renames)
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/files"
        
        response = self.make_request_with_backoff(f"{url}?per_page={per_page}")
        if not response:
            return []

        all_files = response.json() or []
        
        # Handle pagination using Link header
        page_count = 1
        while hasattr(response, "links") and "next" in response.links and page_count < max_pages:
            next_url = response.links["next"]["url"]
            
            response = self.make_request_with_backoff(next_url)
            if response:
                new_files = response.json() or []
                all_files.extend(new_files)
                page_count += 1
            else:
                break
        
        return all_files

    # ============================================================================
    # REVIEW & COMMENT EXTRACTION
    # ============================================================================

    def extract_pr_review_comments(self, pr_id: int) -> List[Dict]:
        """
        Extract review comments (inline code comments) for a pull request.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            List of review comment dictionaries:
            - id, body, user, created_at, updated_at
            - path, position, line, original_position
            - commit_id, original_commit_id
            - in_reply_to_id (for threaded comments)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/comments"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return []
        
        return response.json() or []

    def extract_pr_issue_comments(self, pr_id: int) -> List[Dict]:
        """
        Extract issue comments (general PR comments) for a pull request.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            List of issue comment dictionaries:
            - id, body, user, created_at, updated_at
            - author_association (OWNER, MEMBER, CONTRIBUTOR, etc.)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_id}/comments"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return []
        
        return response.json() or []

    def extract_pr_all_comments(self, pr_id: int) -> Dict[str, List[Dict]]:
        """
        Extract all types of comments for a pull request using parallel requests.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            Dictionary with keys:
            - "review_comments": Inline code review comments
            - "issue_comments": General PR discussion comments
            - "pr_reviews": Review submissions
        """
        # Prepare URLs for parallel fetching
        urls = {
            "review_comments": f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/comments",
            "issue_comments": f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_id}/comments",
            "pr_reviews": f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/reviews"
        }
        
        results = {}
        
        # Fetch all three in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.make_request_with_backoff, url): key 
                for key, url in urls.items()
            }
            
            for future in as_completed(futures):
                key = futures[future]
                try:
                    response = future.result()
                    results[key] = response.json() if response else []
                except Exception as e:
                    print(f"[WARN] Error fetching {key} for PR #{pr_id}: {e}")
                    results[key] = []
        
        return results

    def extract_pr_reviews(self, pr_id: int) -> List[Dict]:
        """
        Extract review submissions for a pull request.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            List of review dictionaries:
            - id, user, body, state (APPROVED, CHANGES_REQUESTED, COMMENTED)
            - submitted_at, commit_id
            - author_association
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_id}/reviews"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return []
        
        return response.json() or []

    # ============================================================================
    # BRANCH EXTRACTION
    # ============================================================================

    def extract_all_branches(
        self, 
        per_page: int = None, 
        max_pages: int = None,
        protected: Optional[bool] = None
    ) -> List[Dict]:
        """
        Extract all branches from the repository.
        
        Args:
            per_page: Results per page (default: 100)
            max_pages: Maximum pages to fetch (default: 50)
            protected: Filter by protected status (True/False/None for all)
            
        Returns:
            List of branch dictionaries:
            - name, commit (sha, url), protected
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/branches"
        all_branches = []
        page = 1
        
        print(f"[INFO] Extracting branches...")
        
        while page <= max_pages:
            params = f"?per_page={per_page}&page={page}"
            if protected is not None:
                params += f"&protected={str(protected).lower()}"
            
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            all_branches.extend(data)
            print(f"[PROGRESS] Page {page}: +{len(data)} branches (total: {len(all_branches)})")
            page += 1
        
        print(f"[INFO] Extracted {len(all_branches)} branches")
        return all_branches

    def extract_branch_details(self, branch_name: str) -> Dict:
        """
        Extract detailed information for a specific branch.
        
        Args:
            branch_name: Branch name
            
        Returns:
            Dictionary containing:
            - name, commit (full commit object), protected
            - protection (detailed protection rules if protected)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/branches/{branch_name}"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return {}
        
        return response.json()

    # ============================================================================
    # COMPARISON & DIFF EXTRACTION
    # ============================================================================

    def compare_commits(self, base: str, head: str) -> Dict:
        """
        Compare two commits/branches using GitHub Compare API.
        
        Args:
            base: Base commit SHA or branch name
            head: Head commit SHA or branch name
            
        Returns:
            Dictionary containing:
            - ahead_by, behind_by (commit counts)
            - status (identical, ahead, behind, diverged)
            - total_commits, commits (list)
            - files (list of changed files)
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/compare/{base}...{head}"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return {}
        
        return response.json()

    # ============================================================================
    # REPOSITORY METADATA
    # ============================================================================

    def extract_repository_info(self) -> Dict:
        """
        Extract basic repository information.
        
        Returns:
            Dictionary containing:
            - name, full_name, description, homepage
            - owner, created_at, updated_at, pushed_at
            - size, stargazers_count, watchers_count, forks_count
            - language, topics, license
            - default_branch, open_issues_count
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
        
        response = self.make_request_with_backoff(url)
        if not response:
            return {}
        
        return response.json()

    def extract_repository_contributors(
        self,
        per_page: int = None,
        max_pages: int = None,
        anon: bool = False
    ) -> List[Dict]:
        """
        Extract repository contributors.
        
        Args:
            per_page: Results per page (default: 100)
            max_pages: Maximum pages to fetch (default: 50)
            anon: Include anonymous contributors
            
        Returns:
            List of contributor dictionaries:
            - login, id, avatar_url, type
            - contributions (commit count)
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contributors"
        all_contributors = []
        page = 1
        
        while page <= max_pages:
            params = f"?per_page={per_page}&page={page}&anon={str(anon).lower()}"
            
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            all_contributors.extend(data)
            page += 1
        
        return all_contributors

    def extract_repository_tags(
        self,
        per_page: int = None,
        max_pages: int = None
    ) -> List[Dict]:
        """
        Extract repository tags (releases).
        
        Args:
            per_page: Results per page (default: 100)
            max_pages: Maximum pages to fetch (default: 50)
            
        Returns:
            List of tag dictionaries:
            - name, zipball_url, tarball_url
            - commit (sha, url)
        """
        per_page = per_page or self.DEFAULT_RESULTS_PER_PAGE
        max_pages = max_pages or self.MAX_PAGES
        
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/tags"
        all_tags = []
        page = 1
        
        while page <= max_pages:
            params = f"?per_page={per_page}&page={page}"
            
            response = self.make_request_with_backoff(url + params)
            if not response:
                break
            
            data = response.json() or []
            if not data:
                break
            
            all_tags.extend(data)
            page += 1
        
        return all_tags

    # ============================================================================
    # BULK EXTRACTION HELPERS
    # ============================================================================

    def extract_pr_complete(self, pr_id: int) -> Dict:
        """
        Extract complete PR data including commits, files, comments, and reviews.
        
        This is a convenience method that makes multiple API calls.
        
        Args:
            pr_id: Pull request number
            
        Returns:
            Dictionary containing:
            - pr_data: Basic PR information
            - commits: List of commits
            - files: List of changed files
            - review_comments: List of review comments
            - issue_comments: List of issue comments
            - reviews: List of review submissions
        """
        print(f"[INFO] Extracting complete data for PR #{pr_id}")
        
        return {
            "pr_data": self.extract_pull_request_by_id(pr_id),
            "commits": self.extract_commits_from_pr(pr_id),
            "files": self.extract_pr_file_changes(pr_id),
            "review_comments": self.extract_pr_review_comments(pr_id),
            "issue_comments": self.extract_pr_issue_comments(pr_id),
            "reviews": self.extract_pr_reviews(pr_id)
        }

    def extract_commit_complete(self, commit_sha: str) -> Dict:
        """
        Extract complete commit data including file changes.
        
        Args:
            commit_sha: Commit SHA hash
            
        Returns:
            Complete commit dictionary with file changes
        """
        return self.extract_commit_details(commit_sha)
    
    # ============================================================================
    # FULL FILE CONTENT EXTRACTION
    # ============================================================================

    def extract_file_content_at_ref(self, path: str, ref: str) -> Optional[str]:
        """
        Extract full file content at a specific commit SHA.

        Args:
            path: Repository-relative file path
            ref: Commit SHA (or other git reference)

        Returns:
         - File content as a UTF-8 string, or
          - None (not a text file / too large / not accessible)
        """
        safe_path = quote(path)
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{safe_path}?ref={ref}"

        response = self.make_request_with_backoff(url)
        if not response:
            return None

        data = response.json() or {}
        if data.get("type") != "file":
            return None

        # Some large files may not have inline content
        if data.get("encoding") != "base64" or "content" not in data:
            return None

        try:
            raw_bytes = base64.b64decode(data["content"])
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return None


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("Pull Request Extractor - Pure Data Extraction")
    print("="*70)
    
    # Initialize extractor
    extractor = PullRequestExtractor(
        repo_owner="microsoft",
        repo_name="vscode",
        need_auth=True  # Uses GITHUB_TOKEN from .env
    )
    
    # Example 1: Extract single PR
    print("\n[1] Extracting single PR...")
    pr_data = extractor.extract_pull_request_by_id(100)
    if pr_data:
        print(f"    PR #{pr_data['number']}: {pr_data['pr_title']}")
        print(f"    State: {pr_data['state']}")
        print(f"    Author: {pr_data['user']['login']}")
    
    # Example 2: Extract PR commits
    print("\n[2] Extracting commits from PR...")
    commits = extractor.extract_commits_from_pr(100)
    print(f"    Found {len(commits)} commits")
    if commits:
        print(f"    First commit: {commits[0]['sha'][:8]} - {commits[0]['commit']['message'][:50]}")
    
    # Example 3: Extract file changes
    print("\n[3] Extracting file changes...")
    files = extractor.extract_pr_file_changes(100)
    print(f"    Found {len(files)} changed files")
    if files:
        print(f"    First file: {files[0]['filename']} (+{files[0]['additions']}/-{files[0]['deletions']})")
    
    # Example 4: Extract all comments
    print("\n[4] Extracting all comments...")
    all_comments = extractor.extract_pr_all_comments(100)
    print(f"    Review comments: {len(all_comments['review_comments'])}")
    print(f"    Issue comments: {len(all_comments['issue_comments'])}")
    
    # Example 5: Extract reviews
    print("\n[5] Extracting reviews...")
    reviews = extractor.extract_pr_reviews(100)
    print(f"    Found {len(reviews)} reviews")
    
    # Example 6: Extract complete PR
    print("\n[6] Extracting complete PR data...")
    complete_pr = extractor.extract_pr_complete(100)
    print(f"    PR: {complete_pr['pr_data']['pr_title'] if complete_pr['pr_data'] else 'N/A'}")
    print(f"    Commits: {len(complete_pr['commits'])}")
    print(f"    Files: {len(complete_pr['files'])}")
    print(f"    Review comments: {len(complete_pr['review_comments'])}")
    print(f"    Issue comments: {len(complete_pr['issue_comments'])}")
    print(f"    Reviews: {len(complete_pr['reviews'])}")
    
    # Example 7: Extract branches
    print("\n[7] Extracting branches...")
    branches = extractor.extract_all_branches(per_page=10, max_pages=1)
    print(f"    Found {len(branches)} branches")
    if branches:
        print(f"    First branch: {branches[0]['name']}")
    
    # Example 8: Compare commits
    print("\n[8] Comparing commits...")
    comparison = extractor.compare_commits("main", "HEAD")
    if comparison:
        print(f"    Ahead by: {comparison.get('ahead_by', 'N/A')}")
        print(f"    Behind by: {comparison.get('behind_by', 'N/A')}")
        print(f"    Status: {comparison.get('status', 'N/A')}")
    
    # Example 9: Repository info
    print("\n[9] Extracting repository info...")
    repo_info = extractor.extract_repository_info()
    if repo_info:
        print(f"    Name: {repo_info.get('full_name', 'N/A')}")
        print(f"    Stars: {repo_info.get('stargazers_count', 'N/A')}")
        print(f"    Language: {repo_info.get('language', 'N/A')}")
    
    # Example 10: Check rate limit
    print("\n[10] Checking rate limit...")
    rate_limit = extractor.get_api_rate_limit_info()
    if rate_limit:
        core = rate_limit.get('resources', {}).get('core', {})
        print(f"    Remaining: {core.get('remaining', 'N/A')}/{core.get('limit', 'N/A')}")
        print(f"    Reset at: {core.get('reset', 'N/A')}")
    
    print("\n" + "="*70)
    print("Testing complete!")
    print("="*70)
    print("\nREMINDER: This module returns RAW data only.")
    print("Apply filters, transformations, and business logic separately.")
    print("="*70)