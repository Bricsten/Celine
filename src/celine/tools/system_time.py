"""The get_current_time tool."""

from datetime import datetime


def get_current_time():
    """Return the current local system time as a string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
