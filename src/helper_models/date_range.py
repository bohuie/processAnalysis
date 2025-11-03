from datetime import date
from typing import Optional

from schema import Schema

from src.utils.datetime_conversion import str_to_date, date_to_str


class DateRange:
    start_date: Optional[str]
    end_date: Optional[str]
    folder_name: Optional[str]

    def __init__(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ):
        self.start_date = start_date
        self.end_date = end_date if end_date is not None else date_to_str(date.today())
        self.folder_name = f"from_{self.start_date if self.start_date is not None else 'start'}_to_{self.end_date}"

    def validate_schema(self):
        Schema(str).validate(self.end_date)
        if self.start_date is not None:
            Schema(str).validate(self.start_date)

            start_date_datetime = str_to_date(self.start_date)
            end_date_datetime = str_to_date(self.end_date)

            if start_date_datetime > end_date_datetime:
                raise ValueError("Start date must be before end date")

    def __post_init__(self):
        self.validate_schema()
