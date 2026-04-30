from datetime import date

import pytest

from data_fetcher.models import ContractSpec, InstrumentType
from data_fetcher.nse_utils import (
    generate_tradingsymbol,
    is_monthly_expiry,
    last_thursday_of_month,
    expiries_in_range,
)


# ── last_thursday_of_month ─────────────────────────────────────────────────

def test_last_thursday_april_2025():
    assert last_thursday_of_month(2025, 4) == date(2025, 4, 24)

def test_last_thursday_december_2024():
    assert last_thursday_of_month(2024, 12) == date(2024, 12, 26)

def test_last_thursday_january_2025():
    assert last_thursday_of_month(2025, 1) == date(2025, 1, 30)


# ── is_monthly_expiry ──────────────────────────────────────────────────────

def test_is_monthly_april_24_2025():
    assert is_monthly_expiry(date(2025, 4, 24)) is True

def test_weekly_is_not_monthly():
    # April 17 is a Thursday but not the last one
    assert is_monthly_expiry(date(2025, 4, 17)) is False

def test_non_thursday_is_not_monthly():
    assert is_monthly_expiry(date(2025, 4, 23)) is False


# ── generate_tradingsymbol ─────────────────────────────────────────────────

def _spec(underlying, expiry, itype, strike=None):
    return ContractSpec(underlying=underlying, expiry=expiry,
                        instrument_type=InstrumentType(itype), strike=strike)


def test_monthly_fut():
    spec = _spec("NIFTY", date(2025, 4, 24), "FUT")
    assert generate_tradingsymbol(spec) == "NIFTY25APRFUT"

def test_monthly_ce():
    spec = _spec("NIFTY", date(2025, 4, 24), "CE", strike=18000.0)
    assert generate_tradingsymbol(spec) == "NIFTY25APR18000CE"

def test_monthly_pe():
    spec = _spec("BANKNIFTY", date(2025, 4, 24), "PE", strike=42000.0)
    assert generate_tradingsymbol(spec) == "BANKNIFTY25APR42000PE"

def test_weekly_ce_april_17():
    # April 17 2025 is a Thursday (weekly)
    spec = _spec("NIFTY", date(2025, 4, 17), "CE", strike=18000.0)
    assert generate_tradingsymbol(spec) == "NIFTY2541718000CE"

def test_weekly_ce_october():
    # October uses month_code "O"; day < 10 gets zero-padded
    spec = _spec("NIFTY", date(2025, 10, 9), "CE", strike=25000.0)
    assert generate_tradingsymbol(spec) == "NIFTY25O0925000CE"

def test_weekly_ce_november():
    spec = _spec("NIFTY", date(2025, 11, 6), "CE", strike=24000.0)
    assert generate_tradingsymbol(spec) == "NIFTY25N0624000CE"

def test_weekly_ce_december():
    spec = _spec("NIFTY", date(2025, 12, 4), "CE", strike=23000.0)
    assert generate_tradingsymbol(spec) == "NIFTY25D0423000CE"

def test_fractional_strike():
    # Half-point strikes must NOT truncate the decimal
    spec = _spec("BANKNIFTY", date(2025, 4, 24), "CE", strike=42050.5)
    assert generate_tradingsymbol(spec) == "BANKNIFTY25APR42050.5CE"

def test_monthly_december_fut():
    spec = _spec("NIFTY", date(2024, 12, 26), "FUT")
    assert generate_tradingsymbol(spec) == "NIFTY24DECFUT"


# ── expiries_in_range ──────────────────────────────────────────────────────

def test_expiries_in_range_includes_both():
    expiries = expiries_in_range(date(2025, 4, 1), date(2025, 4, 30))
    # April 2025 Thursdays: 3, 10, 17, 24 (24 = last Thursday = monthly)
    assert date(2025, 4, 3) in expiries
    assert date(2025, 4, 10) in expiries
    assert date(2025, 4, 17) in expiries
    assert date(2025, 4, 24) in expiries

def test_expiries_monthly_only():
    expiries = expiries_in_range(
        date(2025, 4, 1), date(2025, 4, 30),
        include_weekly=False, include_monthly=True,
    )
    assert expiries == [date(2025, 4, 24)]

def test_expiries_weekly_only():
    expiries = expiries_in_range(
        date(2025, 4, 1), date(2025, 4, 30),
        include_weekly=True, include_monthly=False,
    )
    assert date(2025, 4, 24) not in expiries
    assert date(2025, 4, 17) in expiries
