import os
from dotenv import load_dotenv

"""
    If this throws EnvironmentError, make sure to set
    `PATH_TO_WKHTMLTOPDF` variable in the .env file
    in the root folder.
"""


def get_path_to_wkhtmltopdf() -> str:
    try:
        load_dotenv()
        return os.environ.get("PATH_TO_WKHTMLTOPDF")
    except KeyError:
        raise EnvironmentError("No environment value for PATH_TO_WKHTMLTOPDF")
