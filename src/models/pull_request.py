import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import pytz
from schema import Schema

from src.models.commit import Commit
from src.models.interface import GithubObject
from src.models.pull_request_file import PullRequestFile
from src.models.user import User
from src.utils.anonymize_data import anonymize_mention_in_pr_comment


class PullRequest(GithubObject):
    repo_owner: User
    repo_name: str
    pr_id: int
    commits: List[Commit]
    assignees: List[User]
    reviewers: List[User]
    pr_author: User
    pr_title: str
    pr_description: str
    pr_url: str
    url_html: Optional[str]
    head_branch: Optional[str]
    base_branch: Optional[str]
    state: str
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]
    merged_at: Optional[datetime]
    line_added: int
    line_deleted: int
    line_added_test: int
    line_deleted_test: int
    file_changed: int
    num_commits: int
    comments: Optional[List[Dict]]
    merged_by: Optional[str]
    num_reviewers: int
    mergeable_state: Optional[str]
    is_up_to_date: bool
    has_conflicts: bool
    is_self_merged: bool
    was_up_to_date_at_merge: Optional[bool]
    was_behind_at_merge: Optional[int]



    def __init__(
        self,
        pull_request_json: Dict,
        commits: List[Commit],
        all_changed_files: List[PullRequestFile],
        reviewers: List[User],
        url_html: Optional[str] = None,
        is_from_request: bool = True,
        comments: Optional[List[Dict]] = None,
    ):
        super().__init__(pull_request_json, is_from_request, commits=commits)
        self.reviewers = reviewers
        self.num_reviewers = len(self.reviewers)
        self.url_html = (
            url_html if url_html is not None else pull_request_json.get("url_html")
        )
        self.__aggregate_file_data(all_changed_files)
        self.comments = comments if comments else []
        
    def compute_merge_sync_status(self, extractor=None):
        """
        Computes was_up_to_date_at_merge and was_behind_at_merge
        using GitHub Compare API or placeholder defaults.
        """
        self.was_up_to_date_at_merge = None
        self.was_behind_at_merge = None

        if not hasattr(self, "_raw_data"):
            return self

        merged_at = self._raw_data.get("merged_at")
        merge_commit_sha = self._raw_data.get("merge_commit_sha")
        if not merge_commit_sha and self._raw_data.get("merged_at"):
            # fallback for squash merges
            merge_commit_sha = self._raw_data.get("head", {}).get("sha")

        if not merge_commit_sha or not merged_at:
            # no merge commit available → can’t compare
            self.was_up_to_date_at_merge = None
            self.was_behind_at_merge = None
            return self

        base_sha = self._raw_data.get("base", {}).get("sha")
        
        print(f"[CHECK][PR {getattr(self, 'pr_id', '?')}] base_sha={base_sha} merge_commit_sha={merge_commit_sha}")

        if extractor:
            # use extractor’s request/headers logic
            compare_url = f"https://api.github.com/repos/{extractor.repo_owner}/{extractor.repo_name}/compare/{base_sha}...{merge_commit_sha}"
            res = extractor.make_request_with_backoff(compare_url)
            if res and res.status_code == 200:
                data = res.json()
                self.was_behind_at_merge = data.get("behind_by")
                self.was_up_to_date_at_merge = (data.get("behind_by") == 0)
        else:
            # If extractor not provided, just tag as None
            self.was_up_to_date_at_merge = None
            self.was_behind_at_merge = None

        return self


    def parse_from_request(self, pull_request_json: Dict, **kwargs) -> None:
        self.commits = kwargs.get("commits", [])
        self.reviewers = kwargs.get("reviewers", [])

        # Parse the json
        self.repo_name = pull_request_json.get("head").get("repo").get("name")
        self.repo_owner = User(pull_request_json.get("head").get("repo").get("owner"))
        self.pr_id = pull_request_json.get("number")
        self.head_branch = pull_request_json.get("head", {}).get("ref")
        self.base_branch = pull_request_json.get("base", {}).get("ref")
        
        self.merged_by = None
        if pull_request_json.get("merged_by"):
            self.merged_by = pull_request_json.get("merged_by", {}).get("login", None)

        self.num_reviewers = len(getattr(self, "reviewers", []))
        self.mergeable_state = pull_request_json.get("mergeable_state", "")
        self.is_up_to_date = self.mergeable_state == "clean"
        self.has_conflicts = self.mergeable_state == "dirty"
        self.is_self_merged = False
        if self.merged_by:
            pr_user = (pull_request_json.get("user") or {}).get("login")
            self.is_self_merged = pr_user == self.merged_by

        self.assignees = [
            User(assignee) for assignee in pull_request_json.get("assignees")
        ]
        self.pr_author = User(pull_request_json.get("user"))
        self.pr_title = pull_request_json.get("title")
        self.pr_description = (
            anonymize_mention_in_pr_comment(
                self.remove_images_from_description(pull_request_json.get("body"))
            )
            if pull_request_json.get("body")
            else ""
        )

        self.pr_url = pull_request_json.get("url")
        self.url_html = kwargs.get("url_html", pull_request_json.get("url_html"))
        self.state = pull_request_json.get("state")
        data_tz = pytz.timezone("UTC")
        current_tz = pytz.timezone("America/Vancouver")
        self.created_at = datetime.strptime(
            pull_request_json.get("created_at"), "%Y-%m-%dT%H:%M:%SZ"
        )
        self.created_at = data_tz.localize(self.created_at).astimezone(current_tz)
        self.updated_at = datetime.strptime(
            pull_request_json.get("updated_at"), "%Y-%m-%dT%H:%M:%SZ"
        )
        self.updated_at = data_tz.localize(self.updated_at).astimezone(current_tz)
        self.closed_at = (
            datetime.strptime(pull_request_json.get("closed_at"), "%Y-%m-%dT%H:%M:%SZ")
            if pull_request_json.get("closed_at")
            else None
        )
        self.closed_at = (
            data_tz.localize(self.closed_at).astimezone(current_tz)
            if self.closed_at
            else None
        )
        self.merged_at = (
            datetime.strptime(pull_request_json.get("merged_at"), "%Y-%m-%dT%H:%M:%SZ")
            if pull_request_json.get("merged_at")
            else None
        )
        self.merged_at = (
            data_tz.localize(self.merged_at).astimezone(current_tz)
            if self.merged_at
            else None
        )
        self.num_commits = len(self.commits)
        self.was_up_to_date_at_merge = None
        self.was_behind_at_merge = None


    def validate_request(self, github_json: Dict, **kwargs):
        Schema(str).validate(github_json.get("head").get("repo").get("name"))
        Schema(list).validate(github_json.get("assignees"))
        Schema(int).validate(github_json.get("number"))
        Schema(dict).validate(github_json.get("head").get("repo").get("owner"))
        Schema(dict).validate(github_json.get("user"))
        Schema(str).validate(github_json.get("title"))
        Schema(str).validate(github_json.get("url"))
        if github_json.get("body") is not None:
            Schema(str).validate(github_json.get("body"))
        Schema(str).validate(github_json.get("state"))
        Schema(str).validate(github_json.get("created_at"))
        Schema(str).validate(github_json.get("updated_at"))
        if github_json.get("closed_at") is not None:
            Schema(str).validate(github_json.get("closed_at"))
        if github_json.get("merged_at") is not None:
            Schema(str).validate(github_json.get("merged_at"))

    def parse_from_saved_json(self, pull_request_json: Dict, **kwargs) -> None:
        # Parse the json
        self.repo_name = pull_request_json.get("repo_name")
        self.pr_id = pull_request_json.get("pr_id")
        self.commits = pull_request_json.get("commits")
        self.assignees = [
            User(assignee) for assignee in pull_request_json.get("assignees")
        ]
        self.reviewers = [
            User(reviewer) for reviewer in pull_request_json.get("reviewers")
        ]
        self.repo_owner = User(pull_request_json.get("repo_owner"))
        self.pr_author = User(pull_request_json.get("pr_author"))
        self.pr_title = pull_request_json.get("pr_title")
        self.pr_description = pull_request_json.get("pr_description")
        self.pr_url = pull_request_json.get("pr_url")
        self.url_html = pull_request_json.get("url_html")
        self.state = pull_request_json.get("state")
        self.created_at = datetime.strptime(
            pull_request_json.get("created_at"), "%Y-%m-%dT%H:%M:%SZ"
        )
        self.updated_at = datetime.strptime(
            pull_request_json.get("updated_at"), "%Y-%m-%dT%H:%M:%SZ"
        )
        self.closed_at = (
            datetime.strptime(pull_request_json.get("closed_at"), "%Y-%m-%dT%H:%M:%SZ")
            if pull_request_json.get("closed_at")
            else None
        )
        self.merged_at = (
            datetime.strptime(pull_request_json.get("merged_at"), "%Y-%m-%dT%H:%M:%SZ")
            if pull_request_json.get("merged_at")
            else None
        )
        self.line_added = pull_request_json.get("line_added")
        self.line_deleted = pull_request_json.get("line_deleted")
        self.line_added_test = pull_request_json.get("line_added_test")
        self.line_deleted_test = pull_request_json.get("line_deleted_test")
        self.file_changed = pull_request_json.get("file_changed")
        self.num_commits = pull_request_json.get("num_commits")
        self.merged_by = pull_request_json.get("merged_by")
        self.num_reviewers = pull_request_json.get("num_reviewers")
        self.mergeable_state = pull_request_json.get("mergeable_state")
        self.is_up_to_date = pull_request_json.get("is_up_to_date")
        self.has_conflicts = pull_request_json.get("has_conflicts")
        self.is_self_merged = pull_request_json.get("is_self_merged")
        self.was_up_to_date_at_merge = pull_request_json.get("was_up_to_date_at_merge")
        self.was_behind_at_merge = pull_request_json.get("was_behind_at_merge")


    def validate_saved_json(self, github_json: Dict, **kwargs):
        Schema(dict).validate(github_json)
        Schema(str).validate(github_json.get("repo_name"))
        Schema(int).validate(github_json.get("pr_id"))
        Schema(list).validate(github_json.get("assignees"))
        Schema(list).validate(github_json.get("reviewers"))
        Schema(dict).validate(github_json.get("repo_owner"))
        Schema(dict).validate(github_json.get("pr_author"))
        Schema(list).validate(github_json.get("commits"))
        Schema(str).validate(github_json.get("pr_title"))
        Schema(str).validate(github_json.get("pr_description"))
        Schema(str).validate(github_json.get("pr_url"))
        Schema(str).validate(github_json.get("state"))
        Schema(str).validate(github_json.get("created_at"))
        Schema(str).validate(github_json.get("updated_at"))
        if github_json.get("closed_at") is not None:
            Schema(str).validate(github_json.get("closed_at"))
        if github_json.get("merged_at") is not None:
            Schema(str).validate(github_json.get("merged_at"))

        line_added = github_json.get("line_added", 0)
        line_deleted = github_json.get("line_deleted", 0)
        line_added_test = github_json.get("line_added_test", 0)
        line_deleted_test = github_json.get("line_deleted_test", 0)
        file_changed = github_json.get("file_changed", 0)
        num_commits = github_json.get("num_commits", 0)

        Schema(int).validate(line_added)
        Schema(int).validate(line_deleted)
        Schema(int).validate(line_added_test)
        Schema(int).validate(line_deleted_test)
        Schema(int).validate(file_changed)
        Schema(int).validate(num_commits)
        
        if "was_up_to_date_at_merge" in github_json:
            Schema(bool).validate(github_json.get("was_up_to_date_at_merge"))
        if "was_behind_at_merge" in github_json:
            Schema(int).validate(github_json.get("was_behind_at_merge"))


    def __dict__(self):
        base_dict = {
            "repo_owner": self.repo_owner.todict(),
            "repo_name": self.repo_name,
            "pr_id": self.pr_id,
            "assignees": [assignee.todict() for assignee in self.assignees],
            "reviewers": [reviewer.todict() for reviewer in self.reviewers],
            "pr_author": self.pr_author.todict(),
            "commits": [commit.todict() for commit in self.commits],
            "num_commits": len(self.commits),
            "pr_title": self.pr_title,
            "pr_description": self.pr_description,
            "pr_url": self.pr_url,
            "url_html": self.url_html,
            "head_branch": getattr(self, "head_branch", None),
            "base_branch": getattr(self, "base_branch", None),
            "state": self.state,
            "comments": self.comments,
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "updated_at": self.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "closed_at": self.closed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.closed_at is not None
            else None,
            "merged_at": self.merged_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.merged_at is not None
            else None,
            "line_added": self.line_added,
            "line_deleted": self.line_deleted,
            "line_added_test": self.line_added,
            "line_deleted_test": self.line_deleted,
            "file_changed": self.file_changed,
            "merged_by": self.merged_by,
            "num_reviewers": self.num_reviewers,
            "mergeable_state": self.mergeable_state,
            "is_up_to_date": self.is_up_to_date,
            "has_conflicts": self.has_conflicts,
            "is_self_merged": self.is_self_merged,
            "was_up_to_date_at_merge": getattr(self, "was_up_to_date_at_merge", None),
            "was_behind_at_merge": getattr(self, "was_behind_at_merge", None),

        }

        return base_dict

    def __str__(self):
        return f"[{self.repo_name}] Pull Request #{self.pr_id}"

    def todict(self):
        return self.__dict__()

    def tostring(self):
        return self.__str__()

    def __aggregate_file_data(self, all_changed_files: List[PullRequestFile]):
        test_directory = self.check_test_directory(all_changed_files)

        if len(test_directory) > 0:
            test_files = [
                changed_file
                for changed_file in all_changed_files
                if any(
                    changed_file.file_name.startswith(directory)
                    for directory in test_directory
                )
            ]

            # Aggregate lines added and deleted only for files in the test directory
            self.line_added_test = sum(
                [changed_file.num_line_added for changed_file in test_files]
            )
            self.line_deleted_test = sum(
                [changed_file.num_line_deleted for changed_file in test_files]
            )
        else:
            self.line_added_test = 0
            self.line_deleted_test = 0

        self.line_added = sum(
            [changed_file.num_line_added for changed_file in all_changed_files]
        )
        self.line_deleted = sum(
            [changed_file.num_line_deleted for changed_file in all_changed_files]
        )
        self.file_changed = len(all_changed_files)

    def check_test_directory(self, all_changed_files: List[PullRequestFile]):
        # Check if "*/tests/", "*/test/", or "*/testing/" directories exist anywhere in the changed files
        test_directory = []

        for changed_file in all_changed_files:
            index = None
            if "tests/" in changed_file.file_name:
                index = changed_file.file_name.index("tests/") + len("tests/")
            elif "test/" in changed_file.file_name:
                index = changed_file.file_name.index("test/") + len("test/")
            elif "testing/" in changed_file.file_name:
                index = changed_file.file_name.index("testing/") + len("testing/")
            if index != None:
                if changed_file.file_name[:index] not in test_directory:
                    test_directory.append(changed_file.file_name[:index])

        return test_directory

    def remove_images_from_description(self, description: str) -> str:
        """
        Remove <img> tags from the PR description.
        Without this an error is thrown when generating the PDF report.
        """
        return re.sub(r"<img[^>]*>", "[Image Removed]", description)
