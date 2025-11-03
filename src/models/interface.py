from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Dict, List

from src.utils.file_config import FileConfiguration


@dataclass
class GithubObject(ABC):
    def __init__(self, repository_json: Dict, is_from_request: bool, **kwargs):
        if is_from_request:
            self.validate_request(repository_json, **kwargs)
            self.parse_from_request(repository_json, **kwargs)
        else:
            self.validate_saved_json(repository_json, **kwargs)
            self.parse_from_saved_json(repository_json, **kwargs)

    @abstractmethod
    def parse_from_request(self, repository_json: Dict, **kwargs) -> None:
        raise NotImplementedError("parse_from_request method not implemented")

    @abstractmethod
    def parse_from_saved_json(self, repository_json: Dict, **kwargs) -> None:
        raise NotImplementedError("parse_from_saved_json method not implemented")

    @abstractmethod
    def validate_request(self, github_json: Dict, **kwargs) -> None:
        raise NotImplementedError("validate method not implemented")

    @abstractmethod
    def validate_saved_json(self, github_json: Dict, **kwargs) -> None:
        raise NotImplementedError("validate method not implemented")

    @abstractmethod
    def todict(self) -> Dict:
        raise NotImplementedError("todict method not implemented")

    @abstractmethod
    def tostring(self) -> str:
        raise NotImplementedError("tostring method not implemented")


@dataclass
class GithubObjects(ABC):
    def __init__(self, data: List[GithubObject], fields: List[str]):
        if fields is None:
            fields = self.default_fields()
        self.fields: List[str] = fields
        if len(data) > 0:
            self.validate(data)

    def validate(self, data: List["GithubObject"]):
        """Ensure all expected fields exist in the first object’s dict representation."""
        if not data:
            return

        first_obj = data[0]
        if hasattr(first_obj, "todict"):
            available_fields = set(first_obj.todict().keys())
        else:
            available_fields = set(vars(first_obj).keys())

        for field in self.fields:
            if field not in available_fields:
                print("DEBUG – available fields:", available_fields)
                print("DEBUG – expected fields:", self.fields)
                raise ValueError(f"Field {field} not in data")



    @abstractmethod
    def to_csv(self, config: FileConfiguration) -> str:
        raise NotImplementedError("to_csv method not implemented")

    @staticmethod
    @abstractmethod
    def default_fields() -> List[str]:
        raise NotImplementedError("default_fields method not implemented")
