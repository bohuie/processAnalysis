import json
import os.path
from typing import Dict

from schema import Schema

from src.models.interface import GithubObject
from src.utils.anonymize_data import anonymize_username
from src.utils.file_path import get_anonymized_usernames_file, get_confidential_folder


class User(GithubObject):
    username: str
    account_type: str
    is_admin: bool

    def __init__(self, user_json: Dict, is_from_request: bool = True):
        super().__init__(user_json, is_from_request)

    def parse_from_request(self, user_json: Dict, **kwargs) -> None:
        # self.username = user_json.get("login")
        self.username = anonymize_username(user_json.get("login"))
        self.account_type = user_json.get("type")
        self.is_admin = user_json.get("site_admin")

    def validate_request(self, user_json: Dict, **kwargs):
        # Ensure that 'id' is present and valid
        Schema(int).validate(user_json["id"])  # Force validation for 'id'
        Schema(str).validate(user_json.get("login"))

        # Ensure that 'type' has a default value if it is None
        user_type = user_json.get("type", "User")  # Default to "User" if None
        Schema(str).validate(user_type)

        site_admin = user_json.get("site_admin", False)
        Schema(bool).validate(site_admin)

    def parse_from_saved_json(self, user_json: Dict, **kwargs) -> None:
        self.username = user_json.get("username")
        self.account_type = user_json.get("account_type")
        self.is_admin = user_json.get("is_admin")

    def validate_saved_json(self, user_json: Dict, **kwargs) -> None:
        Schema(str).validate(user_json.get("username"))
        Schema(str).validate(user_json.get("account_type"))
        Schema(bool).validate(user_json.get("is_admin"))

    def __str__(self):
        return f"{self.account_type.capitalize()}: {self.username}"

    def __dict__(self):
        return {
            "username": self.username,
            "account_type": self.account_type,
            "is_admin": self.is_admin,
        }

    def todict(self) -> Dict:
        return self.__dict__()

    def tostring(self) -> str:
        return self.__str__()

    def _deanonymize_username(self):
        if os.path.exists(get_confidential_folder()):
            anonymized_usernames_path = get_anonymized_usernames_file()
            if os.path.exists(anonymized_usernames_path):
                with open(anonymized_usernames_path, "r") as f:
                    anonymized_usernames = json.load(f)
                    for deanonymized, anonymized in anonymized_usernames.items():
                        if self.username == anonymized:
                            return deanonymized
        return self.username
