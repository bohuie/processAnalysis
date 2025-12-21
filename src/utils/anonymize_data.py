import hashlib
import json

from json import JSONDecodeError
from src.utils.file_path import get_anonymized_usernames_file, get_confidential_folder


def _load_mapping() -> dict:
    """
    Safely load the anonymized_usernames mapping.

    - If the file does not exist, return {}.
    - If the file exists but is empty or invalid JSON, return {}.
    - If the JSON is not a dict, also return {}.
    """
    path = get_anonymized_usernames_file()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        # If it's not a dict, treat as empty mapping
        return {}
    except FileNotFoundError:
        return {}
    except (JSONDecodeError, ValueError):
        # Empty file or corrupted JSON
        return {}


def _save_mapping(mapping: dict) -> None:
    """
    Persist the anonymized_usernames mapping back to disk,
    ensuring the confidential folder exists.
    """
    confidential_folder = get_confidential_folder()
    if not confidential_folder.exists():
        confidential_folder.mkdir(parents=True, exist_ok=True)

    path = get_anonymized_usernames_file()
    with open(path, "w") as f:
        json.dump(mapping, f)


def anonymize_mention_in_pr_comment(text: str) -> str:
    """
    Replace @real_user with @fake_user in PR comments,
    based on the anonymized_usernames mapping.
    Safe if the mapping file is missing/empty.
    """
    anonymized_usernames = _load_mapping()
    for username, fake in anonymized_usernames.items():
        text = text.replace(f"@{username}", f"@{fake}")
    return text


def anonymize_username(username: str) -> str:
    """
    Map a real username to a stable fake username.

    - Robust to missing/empty/corrupt anonymized_usernames.json.
    - Uses your existing first/last-character name scheme + short hash.
    """
    anonymized_usernames = _load_mapping()

    # If already anonymized, just return it
    if username in anonymized_usernames:
        return anonymized_usernames[username]

    fake_names = {
        "a": "Alex",
        "b": "Blake",
        "c": "Casey",
        "d": "Dana",
        "e": "Elliot",
        "f": "Finley",
        "g": "Gray",
        "h": "Hayden",
        "i": "Indigo",
        "j": "Jordan",
        "k": "Kai",
        "l": "Logan",
        "m": "Morgan",
        "n": "Nico",
        "o": "Oakley",
        "p": "Peyton",
        "q": "Quinn",
        "r": "River",
        "s": "Skyler",
        "t": "Taylor",
        "u": "Uma",
        "v": "Vesper",
        "w": "Wren",
        "x": "Xander",
        "y": "Yara",
        "z": "Zane",
        "1": "1",
        "2": "2",
        "3": "3",
        "4": "4",
        "5": "5",
        "6": "6",
        "7": "7",
        "8": "8",
        "9": "9",
    }

    print(f"Anonymizing username: {username}")

    # Base name from first + last character of username
    first = fake_names.get(username[0].lower(), username[0].lower())
    last = fake_names.get(username[-1].lower(), username[-1].lower())
    base = f"{first}{last}"

    # Short stable hash for uniqueness
    hash_object = hashlib.sha256(username.encode())
    unique_hash = hash_object.hexdigest()[:4]  # first 4 chars for brevity

    fake_username = f"{base}-{unique_hash}"

    anonymized_usernames[username] = fake_username
    _save_mapping(anonymized_usernames)

    return fake_username
