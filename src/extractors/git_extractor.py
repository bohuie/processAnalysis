import os
import pandas as pd
import requests
import json
import csv
from pathlib import Path
from src.utils.request_counter import RequestCounter
from src.utils.filename import construct_file_name
from src.utils.file_path import get_project_data_json_folder
from src.utils.github_url import (
    get_github_token,
    get_github_repository_url,
    get_github_repo_url_for_project_by_project_id,
)
from src.models.repository import Repository
from src.utils.list_repos import get_org_repositories
from src.utils.file_path import get_project_data_csv_folder


class GitExtractor:
    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        need_auth: bool = True,
        request_counter: RequestCounter = None,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.header = (
            ({"Authorization": "token " + get_github_token()}) if need_auth else {}
        )
        if request_counter is None:
            self.request_counter = RequestCounter()
        else:
            self.request_counter = request_counter
        self.need_auth = need_auth

        self.csv_filepath = ""

    def extract_repository(
        self, save_data_to_json: bool = True, save_data_to_csv: bool = True
    ) -> Repository:
        print(f"Fetching repository data for {self.repo_owner}/{self.repo_name}")
        url = get_github_repository_url(self.repo_owner, self.repo_name)

        try:
            res = requests.get(url, headers=self.header)
            self.request_counter.increment()
            res.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(
                f"An issue happened while fetching the repository data:\n{err}"
            )

        data = res.json()
        repository = Repository(data)

        if save_data_to_json:
            out_filename = construct_file_name(self.repo_owner, self.repo_name, "repo")
            out_filepath = os.path.join(get_project_data_json_folder(), out_filename)

            with open(out_filepath, "w") as outfile:
                json.dump(repository.todict(), outfile, indent=2)

        if save_data_to_csv:
            self.save_repository_to_csv(repository)

        return repository

    def save_repository_to_csv(self, repository):
        rows = []
        repo_data = repository.todict()

        # Print repo_data for debugging
        print(f"[DEBUG] Repository Data being saved to CSV: {repo_data}")
        rows.append({})
        for key, value in repo_data.items():
            if isinstance(value, dict):  # If it's nested dictionary, unpack it
                for k, v in value.items():
                    rows[-1][k] = v
            else:
                rows[-1][key] = value

        # Create a DataFrame from the rows
        df = pd.DataFrame(rows)

        # Save the DataFrame to a CSV file
        csv_filename = (
            construct_file_name(self.repo_owner, self.repo_name, "repo") + ".csv"
        )
        csv_filepath = get_project_data_csv_folder() / csv_filename
        df.to_csv(csv_filepath, index=False, encoding="utf-8")

    def extract_owner_from_project(self, project_id: int) -> Repository:
        url = get_github_repo_url_for_project_by_project_id(project_id)

        try:
            res = requests.get(url, headers=self.header)
            self.request_counter.increment()
            res.raise_for_status()
        except requests.exceptions.HTTPError as err:
            raise SystemExit(f"An issue happens when fetch for project owner:\n{err}")
        data = res.json()
        repo = Repository(data)
        return repo


if __name__ == "__main__":
    ORG_NAME = ""  # GitHub Classroom organization name

    # Fetch repositories from the GitHub Classroom organization
    print(f"\n[INFO] Fetching repositories for organization: {ORG_NAME}")
    repos = get_org_repositories(ORG_NAME)
    print(f"[INFO] Total repositories found: {len(repos)}")

    # Define the range of team repositories you want to process
    TARGET_REPOS = [f"year-long-project-team-{i}" for i in range(1, 24)]

    for repo in repos:
        repo_name = repo["name"]

        # Only process repositories that match the desired naming pattern
        if repo_name in TARGET_REPOS:
            print(f"\n[INFO] Processing repository: {repo_name}")

            git_extractor = GitExtractor(repo_owner=ORG_NAME, repo_name=repo_name)

            try:
                # Extract the repository data and save it to JSON and CSV
                repo_data = git_extractor.extract_repository(
                    save_data_to_json=True, save_data_to_csv=True
                )
                print(f"[INFO] Successfully extracted data for {repo_name}")
            except Exception as e:
                print(f"[ERROR] Failed to extract data for {repo_name}: {e}")
        else:
            print(f"[INFO] Skipping repository: {repo_name}, not in target list.")
