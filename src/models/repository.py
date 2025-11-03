from typing import Dict, List

from schema import Schema

from src.models.user import User
from src.models.interface import GithubObject


class Repository(GithubObject):
    repo_name: str
    repo_owner: User
    is_public: bool
    has_issues: bool
    has_projects: bool
    collaborators: List[Dict]

    def __init__(self, repository_json: Dict, is_from_request: bool = True):
        super().__init__(repository_json, is_from_request)

    def parse_from_request(self, repository_json: Dict, **kwargs) -> None:
        self.repo_name = repository_json.get("name")
        self.repo_owner = User(repository_json.get("owner"))
        self.is_public = repository_json.get("visibility") == "public"

        self.has_issues = repository_json.get("has_issues")
        self.has_projects = repository_json.get("has_projects")

        # TODO: Fetch the list of collaborators and add here (
        #  https://docs.github.com/en/rest/collaborators/collaborators?apiVersion=2022-11-28#list-repository-collaborators)
        self.collaborators = []

    def validate_request(self, repository_json: Dict, **kwargs):
        Schema(str).validate(repository_json.get("name"))
        Schema(dict).validate(repository_json.get("owner"))
        Schema(str).validate(repository_json.get("visibility"))
        Schema(bool).validate(repository_json.get("has_issues"))
        Schema(bool).validate(repository_json.get("has_projects"))

    def parse_from_saved_json(self, repository_json: Dict, **kwargs) -> None:
        self.repo_name = repository_json.get("repo_name")
        self.repo_owner = User(repository_json.get("repo_owner"), is_from_request=False)
        self.is_public = repository_json.get("is_public")
        self.has_issues = repository_json.get("has_issues")
        self.has_projects = repository_json.get("has_projects")
        self.collaborators = repository_json.get("collaborators")

    def validate_saved_json(self, repository_json: Dict, **kwargs):
        Schema(str).validate(repository_json.get("repo_name"))
        Schema(dict).validate(repository_json.get("repo_owner"))
        Schema(bool).validate(repository_json.get("is_public"))
        Schema(bool).validate(repository_json.get("has_issues"))
        Schema(bool).validate(repository_json.get("has_projects"))
        Schema(list).validate(repository_json.get("collaborators"))

    def __dict__(self):
        return {
            "repo_name": self.repo_name,
            "repo_owner": self.repo_owner.todict(),
            "is_public": self.is_public,
            "has_issues": self.has_issues,
            "has_projects": self.has_projects,
            "collaborators": self.collaborators,
        }

    def __str__(self):
        return f"Repository: {self.repo_name}"

    def todict(self):
        return self.__dict__()

    def tostring(self):
        return self.__str__()
