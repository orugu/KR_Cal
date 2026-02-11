"""Holiday provider wrapper using the `holidays` library.
Provides a small adapter to fetch Korean public holidays.
"""
from typing import Dict
import datetime

try:
    import holidays
except Exception:  # pragma: no cover
    holidays = None


class HolidaysProvider:
    def __init__(self, years=None):
        self.years = years or []

    def get_holidays(self) -> Dict[datetime.date, str]:
        """Return a mapping of date -> holiday name for Korea.

        Uses `holidays.KR` if available. If not installed, returns an empty dict.
        """
        if holidays is None:
            return {}

        kr = holidays.KR(years=self.years)
        result = {}
        for d, name in kr.items():
            if isinstance(d, datetime.date):
                result[d] = name
        return result
