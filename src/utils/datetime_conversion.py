from datetime import date, datetime

import pytz

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def str_to_date(date_str: str) -> date:
    """Converts a string to a date object

    Parameters
    ----------
    date_str : str
        A string to convert to a datetime object

    """
    return datetime.strptime(date_str, "%Y-%m-%d")


def date_to_str(date_obj: date) -> str:
    """Converts a date object to a string

    Parameters
    ----------
    date_obj : date
        A datetime object to convert to a string

    """
    return date_obj.strftime("%Y-%m-%d")


def str_to_datetime(datetime_str: str) -> datetime:
    """Converts a string to a datetime object

    Parameters
    ----------
    datetime_str : str
        A string to convert to a datetime object

    """
    return datetime.strptime(datetime_str, DATETIME_FORMAT)


def datetime_to_timezone(datetime_obj: datetime, timezone: str) -> datetime:
    """Converts a datetime object to a different timezone without changing the time

    Parameters
    ----------
    datetime_obj : datetime
        A datetime object to convert to a different timezone
    timezone : str
        The timezone to convert to

    """
    return datetime_obj.replace(tzinfo=pytz.timezone(timezone))


def datetime_to_localize(
    datetime_obj: datetime, from_timezone: str, to_timezone: str
) -> datetime:
    """Converts a datetime object to a localized timezone

    Parameters
    ----------
    datetime_obj : datetime
        A datetime object to localize

    """
    data_tz = pytz.timezone(from_timezone)
    current_tz = pytz.timezone(to_timezone)

    return data_tz.localize(datetime_obj).astimezone(current_tz)


def datetime_to_str(datetime_obj: datetime) -> str:
    """Converts a datetime object to a string

    Parameters
    ----------
    datetime_obj : datetime
        A datetime object to convert to a string

    """
    return datetime_obj.strftime(DATETIME_FORMAT)


def datetime_difference_in_days(
    start_datetime: datetime, end_datetime: datetime
) -> float:
    """

    :param start_datetime:
    :param end_datetime:
    :return: The difference in time in a float of days
    """
    time_difference = end_datetime - start_datetime
    days = time_difference.days
    seconds = time_difference.seconds
    total = days + seconds / (24 * 60 * 60)
    return total
