import requests
from src.utils.github_url import get_github_token

ORG_NAME = ""  # Replace with your GitHub Classroom organization name


def get_org_repositories(org_name):
    url = f"https://api.github.com/orgs/{org_name}/repos"
    headers = {"Authorization": f"token {get_github_token()}"}

    all_repos = []
    params = {
        "per_page": 100,  # Maximum allowed per page
        "type": "all",  # Fetch all repositories (public, private, forks, sources, etc.)
    }

    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            repos = response.json()
            all_repos.extend(repos)
            # Check for pagination: GitHub uses the 'Link' header for pagination
            if "next" in response.links:
                url = response.links["next"]["url"]
            else:
                url = None
        else:
            print(
                f"Failed to fetch repositories: {response.status_code} - {response.text}"
            )
            return []

    return all_repos


if __name__ == "__main__":
    repos = get_org_repositories(ORG_NAME)
    if repos:
        print(f"Total repositories found: {len(repos)}")
        for repo in repos:
            print(f"Repository: {repo['name']}")
