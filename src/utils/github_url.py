import datetime
import os

import requests
from dotenv import load_dotenv

from src.utils.datetime_conversion import datetime_to_str


def join_url(*args):
    return "/".join(arg.strip("/") for arg in args)


def get_github_token() -> str:
    try:
        load_dotenv()
        return os.environ.get("GITHUB_TOKEN")
    except KeyError:
        raise EnvironmentError("No environment value for GITHUB_TOKEN")


def get_github_base_url() -> str:
    return "https://api.github.com/"


def get_github_repository_url(owner: str, repo_name: str) -> str:
    return join_url(get_github_base_url(), "repos", owner, repo_name)


def get_github_pull_requests_url(
    owner: str,
    repo_name: str,
    pull_request_status="all",
    results_per_page=100,
) -> str:
    return (
        join_url(get_github_repository_url(owner, repo_name), "pulls")
        + f"?state={pull_request_status}&per_page={results_per_page}"
    )


def get_commits_by_day_url(
    owner: str, repo_name: str, start_date: str, end_date: str
) -> str:
    return (
        join_url(
            get_github_repository_url(owner, repo_name),
            "commits",
        )
        + f"?since={start_date}&until={end_date}"
    )


def get_name_from_username(username: str) -> str:
    return join_url(
        get_github_base_url(),
        "users",
        username,
    )


def get_sorted_github_pull_requests_url(
    owner: str,
    repo_name: str,
    pull_request_status="all",
    results_per_page=100,
    sort="updated",
) -> str:
    return (
        join_url(get_github_repository_url(owner, repo_name), "pulls")
        + f"?state={pull_request_status}&per_page={results_per_page}&sort={sort}"
    )


def get_github_issues_url(
    owner: str, repo_name: str, issue_status="all", results_per_page=100
) -> str:
    return (
        join_url(get_github_repository_url(owner, repo_name), "issues")
        + f"?state={issue_status}&per_page={results_per_page}"
    )


def get_github_pull_request_url_by_id(
    owner: str, repo_name: str, pull_request_id: int
) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name), "pulls", str(pull_request_id)
    )


def get_github_issue_url_by_number(
    owner: str, repo_name: str, issue_number: str
) -> str:
    return join_url(get_github_repository_url(owner, repo_name), "issues", issue_number)


def get_github_commits_of_pr_id_url(
    owner: str, repo_name: str, pull_request_id: int
) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name),
        "pulls",
        str(pull_request_id),
        "commits",
    )


def get_github_commits_of_pr_id_html_url(
    owner: str, repo_name: str, pull_request_id: int
) -> str:
    return join_url(
        "https://github.com",
        owner,
        repo_name,
        "pull",
        str(pull_request_id),
    )


def get_github_comments_for_repo_url(
    owner: str, repo_name: str, results_per_page=100
) -> str:
    return (
        join_url(get_github_repository_url(owner, repo_name), "pulls", "comments")
        + f"?per_page={results_per_page}"
    )


def get_date_filtered_github_comments_for_repo_url(
    owner: str, repo_name: str, results_per_page=100, since_date: datetime = None
) -> str:
    if since_date is None:
        return get_github_comments_for_repo_url(owner, repo_name, results_per_page)

    return (
        join_url(get_github_repository_url(owner, repo_name), "pulls", "comments")
        + f"?per_page={results_per_page}&since={datetime_to_str(since_date)}"
    )


def get_github_review_comments_of_pr_id_url(
    owner: str,
    repo_name: str,
    pull_number: int,
    results_per_page=100,
) -> str:
    return (
        join_url(
            get_github_repository_url(owner, repo_name),
            "pulls",
            str(pull_number),
            "reviews",
        )
        + "?per_page="
        + str(results_per_page)
    )


def get_github_log_report_url(
    owner: str,
    repo_name: str,
    path: str,
    branch: str,
) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name),
        "contents",
        path + "?ref=" + branch,
    )


def get_github_commit_by_branch(
    owner: str,
    repo_name: str,
    path: str,
    branch: str,
) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name),
        "commits?path=" + path + "&sha=" + branch,
    )


def get_github_all_changed_files_of_pr_id_url(
    owner: str,
    repo_name: str,
    pull_number: int,
    results_per_page=100,
) -> str:
    return (
        join_url(
            get_github_repository_url(owner, repo_name),
            "pulls",
            str(pull_number),
            "files",
        )
        + "?per_page="
        + str(results_per_page)
    )


def get_github_review_comments_of_issue_id_url(
    owner: str,
    repo_name: str,
    issue_number: int,
) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name),
        "issues",
        str(issue_number),
        "comments",
    )


def get_github_card_url_by_id(
    card_id: int,
) -> str:
    return os.path.join(
        get_github_base_url(), "projects", "columns", "cards", str(card_id)
    )


def get_github_issue_for_card_by_card_id(
    card_id: int,
) -> str:
    url = get_github_card_url_by_id(card_id)
    try:
        res = requests.get(url)
        res.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise SystemExit(f"An issue happens when fetch for card:\n{err}")
    data = res.json()
    return data.get("content_url")


def get_github_cards_url_for_column_by_column_id(
    column_id: int,
) -> str:
    return join_url(
        "projects",
        "columns",
        str(column_id),
        "cards",
    )


def get_github_timeline_for_issue(owner: str, repo_name: str, issue_number: int) -> str:
    return join_url(
        get_github_repository_url(owner, repo_name),
        "issues",
        str(issue_number),
        "timeline",
    )


def get_github_column_url_by_id(
    column_id: int,
) -> str:
    return join_url(get_github_base_url(), "projects", "columns", str(column_id))


def get_github_columns_url_for_project_by_project_id(
    project_id: int,
) -> str:
    return join_url(
        "projects",
        str(project_id),
        "columns",
    )


def get_github_project_url_by_id(
    project_id: int,
) -> str:
    return join_url(get_github_base_url(), "projects", str(project_id))


def get_github_repo_url_for_project_by_project_id(
    project_id: int,
) -> str:
    url = get_github_project_url_by_id(project_id)
    try:
        res = requests.get(url)
        res.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise SystemExit(f"An issue happens when fetch for project:\n{err}")
    data = res.json()
    return data.get("owner_url")


def get_github_pr_for_issue_by_issue_number(
    owner: str, repo_name: str, issue_number: str
) -> str:
    url = get_github_issue_url_by_number(owner, repo_name, issue_number)
    try:
        res = requests.get(url)
        res.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise SystemExit(f"An issue happens when fetch for pr:\n{err}")
    data = res.json()
    pull = data.get("pull_request")
    return pull["url"]


def get_github_project_url(owner: str, repo: str) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/projects"


def get_github_graphql_url():
    return f"https://api.github.com/graphql"


def get_github_org_projects_url(org_name: str) -> str:
    """
    Construct the URL for fetching organization-level projects.

    Args:
        org_name (str): The name of the GitHub organization.

    Returns:
        str: The constructed URL for the GitHub organization projects API.
    """
    return f"https://api.github.com/orgs/{org_name}/projects"
