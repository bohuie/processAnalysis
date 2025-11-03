from typing import Dict

from schema import Schema

from src.models.interface import GithubObject


class PullRequestFile(GithubObject):
    file_name: str
    num_line_added: int
    num_line_deleted: int

    def __init__(self, pull_request_file: Dict, is_from_request: bool = True, **kwargs):
        super().__init__(pull_request_file, is_from_request, **kwargs)
        if not is_from_request:
            raise ValueError("PullRequestFile object should not be saved as json")

    def parse_from_request(self, github_json: Dict, **kwargs) -> None:
        self.file_name = github_json.get("filename")
        self.num_line_added = github_json.get("additions")
        self.num_line_deleted = github_json.get("deletions")

    def validate_request(self, github_json: Dict, **kwargs):
        Schema(str).validate(github_json.get("filename"))
        Schema(int).validate(github_json.get("additions"))
        Schema(int).validate(github_json.get("deletions"))

    def parse_from_saved_json(self, repository_json: Dict, **kwargs) -> None:
        raise NotImplementedError("PullRequestFile object should not be saved as json")

    def validate_saved_json(self, github_json: Dict, **kwargs) -> None:
        raise NotImplementedError("PullRequestFile object should not be saved as json")

    def todict(self) -> Dict:
        return {
            "file_name": self.file_name,
            "num_line_added": self.num_line_added,
            "num_line_deleted": self.num_line_deleted,
        }

    def tostring(self) -> str:
        return f"{self.file_name}: {self.num_line_added}++ {self.num_line_deleted}--"
