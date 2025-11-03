from datetime import datetime
from typing import Dict, Optional

from schema import Schema

from src.models.interface import GithubObject
from src.models.user import User


class Commit(GithubObject):
    sha: str
    author: Optional[User]
    message: str
    datetime: datetime

    def __init__(self, commit_json: Dict, is_from_request: bool = True):
        super().__init__(commit_json, is_from_request)

    def parse_from_request(self, commit_json: Dict, **kwargs) -> None:
        # Parse the data
        self.sha = commit_json.get("sha")
        self.author = (
            User(commit_json.get("author"))
            if commit_json.get("author") is not None
            else None
        )
        self.message = commit_json.get("commit").get("message")
        self.datetime = datetime.strptime(
            commit_json.get("commit").get("author").get("date"),
            "%Y-%m-%dT%H:%M:%SZ",
        )

    def validate_request(self, commit_json: Dict, **kwargs):
        Schema(str).validate(commit_json.get("sha"))
        if commit_json.get("author") is not None:
            Schema(dict).validate(commit_json.get("author"))
        Schema(str).validate(commit_json.get("commit").get("message"))
        Schema(str).validate(commit_json.get("commit").get("author").get("date"))

    def parse_from_saved_json(self, commit_json: Dict, **kwargs) -> None:
        self.sha = commit_json.get("sha")
        self.author = User(commit_json.get("author"), is_from_request=False)
        self.message = commit_json.get("message")
        self.datetime = datetime.strptime(
            commit_json.get("datetime"), "%Y-%m-%d %H:%M:%S"
        )

    def validate_saved_json(self, commit_json: Dict, **kwargs):
        Schema(str).validate(commit_json.get("sha"))
        Schema(dict).validate(commit_json.get("author"))
        Schema(str).validate(commit_json.get("message"))
        Schema(str).validate(commit_json.get("datetime"))

    def __dict__(self):
        return {
            "sha": self.sha,
            "author": self.author.todict() if self.author is not None else None,
            "message": self.message,
            "datetime": str(self.datetime),
        }

    def __str__(self):
        return f"Commit: {self.sha}"

    def todict(self):
        return self.__dict__()

    def tostring(self):
        return self.__str__()

    def get_commit_string(self):
        return f'@{self.author._deanonymize_username() if self.author is not None else "unknownAuthor"} - {self.message}'
