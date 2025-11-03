import hashlib
import json

import faker

from src.utils.file_path import get_anonymized_usernames_file, get_confidential_folder


def anonymize_mention_in_pr_comment(text: str) -> str:
    with open(get_anonymized_usernames_file(), "r") as f:
        anonymized_usernames = json.load(f)
        for username in anonymized_usernames:
            text = text.replace(f"@{username}", f"@{anonymized_usernames[username]}")
    return text


def anonymize_username(username: str):
    # Create a json file to store the anonymized usernames
    confidential_folder = get_confidential_folder()
    if not confidential_folder.exists():
        confidential_folder.mkdir(parents=True, exist_ok=True)
    anonymized_usernames_path = get_anonymized_usernames_file()
    if not anonymized_usernames_path.exists():
        with open(anonymized_usernames_path, "w") as f:
            json.dump({}, f)

    # Load the anonymized usernames
    with open(anonymized_usernames_path, "r") as f:
        anonymized_usernames = json.load(f)
    # Check if the username is already anonymized
    if username in anonymized_usernames:
        return anonymized_usernames[username]
    else:
        # Generate a fake username and check if it already exists

        # Comine two names, based on the first letter and the last letter of the username
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
        fake_username = fake_names.get(
            username[0].lower(), username[0].lower()
        ) + fake_names.get(username[-1].lower(), username[-1].lower())
        hash_object = hashlib.sha256(username.encode())
        unique_hash = hash_object.hexdigest()[:4]  # first 4 characters for brevity

        # Combine name, length, and hash
        fake_username = f"{fake_username}-{unique_hash}"
        anonymized_usernames[username] = fake_username
        # Save the anonymized usernames
        with open(anonymized_usernames_path, "w") as f:
            json.dump(anonymized_usernames, f)
        return fake_username
