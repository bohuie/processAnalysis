from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).parent.parent.parent


def get_project_data_folder():
    return get_project_root() / "data"


def get_project_data_json_folder():
    return get_project_data_folder() / "json"


def get_project_data_csv_folder():
    return get_project_data_folder() / "csv"


def get_project_data_pdf_folder():
    return get_project_data_folder() / "pdf"


def get_confidential_folder():
    return get_project_root() / "confidential"


def get_anonymized_usernames_file():
    return get_confidential_folder() / "anonymized_usernames.json"


def get_image_folder():
    return get_project_data_folder() / "images"
