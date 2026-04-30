from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_fetcher.models import ContractSpec

# Month abbreviations for monthly expiry tradingsymbols: NIFTY25APRFUT
_MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

# Single-character month codes for weekly expiry tradingsymbols: NIFTY2541718000CE
# NSE uses O/N/D for Oct/Nov/Dec to keep the code 1 character
_WEEKLY_MONTH_CODE = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
}


def last_thursday_of_month(year: int, month: int) -> date:
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    offset = (last_day.weekday() - 3) % 7  # 3 = Thursday
    return last_day - timedelta(days=offset)


def is_monthly_expiry(expiry: date) -> bool:
    return expiry == last_thursday_of_month(expiry.year, expiry.month)


def _format_strike(strike: float) -> str:
    if strike == int(strike):
        return str(int(strike))
    return str(strike)


def generate_tradingsymbol(spec: ContractSpec) -> str:
    """
    Generate the NSE standard tradingsymbol for a contract.

    Monthly FUT:     NIFTY25APRFUT
    Monthly option:  NIFTY25APR18000CE
    Weekly option:   NIFTY2541718000CE  (YY + single-char month + day + strike + type)
    """
    underlying = spec.underlying
    expiry = spec.expiry
    yy = str(expiry.year)[-2:]

    if spec.is_future:
        mon = _MONTH_ABBR[expiry.month]
        return f"{underlying}{yy}{mon}FUT"

    if is_monthly_expiry(expiry):
        mon = _MONTH_ABBR[expiry.month]
        strike_str = _format_strike(spec.strike)  # type: ignore[arg-type]
        return f"{underlying}{yy}{mon}{strike_str}{spec.instrument_type.value}"

    # Weekly option — day is always 2 digits (zero-padded) per NSE format
    month_code = _WEEKLY_MONTH_CODE[expiry.month]
    day_str = f"{expiry.day:02d}"
    strike_str = _format_strike(spec.strike)  # type: ignore[arg-type]
    return f"{underlying}{yy}{month_code}{day_str}{strike_str}{spec.instrument_type.value}"


def expiries_in_range(
    from_date: date,
    to_date: date,
    include_weekly: bool = True,
    include_monthly: bool = True,
) -> list[date]:
    """Return all NSE expiry Thursdays in [from_date, to_date]."""
    thursdays: list[date] = []
    d = from_date
    while d <= to_date:
        if d.weekday() == 3:  # Thursday
            monthly = is_monthly_expiry(d)
            if (include_monthly and monthly) or (include_weekly and not monthly):
                thursdays.append(d)
        d += timedelta(days=1)
    return thursdays
