from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.helper_models.date_range import DateRange
from src.utils.file_path import get_project_data_csv_folder


@dataclass
class FileConfiguration(ABC):
    def __init__(
        self, folder_path: Optional[Path] = None, file_name: Optional[str] = None
    ):
        super().__init__(),

        self.file_name = file_name
        self.folder_path = (
            folder_path if folder_path is not None else get_project_data_csv_folder()
        )


@dataclass
class CSVFileConfiguration(FileConfiguration):
    def __init__(
        self,
        delimiter: str = ",",
        quotechar: str = '"',
        lineterminator: str = "\n",
        index: bool = True,
        header: bool = True,
        excluded_columns: List[str] = None,
        folder_path: Optional[Path] = None,
        file_name: Optional[str] = None,
        date_ranges: List[DateRange] = None,
        datetime_start_column_name: str = "created_at",
        datetime_end_column_name: str = None,
    ):
        super().__init__(folder_path, file_name)

        if excluded_columns is None:
            excluded_columns = []
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.index = index
        self.lineterminator = lineterminator
        self.header = header
        self.excluded_columns = excluded_columns
        self.date_ranges = (
            date_ranges if date_ranges is not None else [DateRange(None, None)]
        )
        self.datetime_start_column_name = datetime_start_column_name
        self.datetime_end_column_name = datetime_end_column_name


@dataclass
class JSONFileConfiguration(FileConfiguration):
    def __init__(
        self,
        indent: int = 2,
        folder_path: Optional[Path] = None,
        file_name: Optional[str] = None,
    ):
        super().__init__(folder_path, file_name)
        self.indent = indent
