"""
Tests for instruments/bhavcopy.py.
Uses real bhavcopy files from ~/development/market_data/bhavcopy.
Tests are skipped automatically if the files are not present.
"""
from datetime import date
from pathlib import Path

import pytest

BHAVCOPY_DIR = Path.home() / "development" / "market_data" / "bhavcopy"
HAS_BHAVCOPY = BHAVCOPY_DIR.exists() and any(BHAVCOPY_DIR.rglob("*_NSEFO.csv"))

pytestmark = pytest.mark.skipif(not HAS_BHAVCOPY, reason="bhavcopy files not present")

from data_fetcher.instruments.bhavcopy import (
    BhavCopyNotFoundError,
    _bhavcopy_path,
    _find_bhavcopy,
    contracts_for_expiry,
    strikes_for_expiry,
)
from data_fetcher.models import InstrumentType


# ── path helpers ───────────────────────────────────────────────────────────

def test_bhavcopy_path_format():
    p = _bhavcopy_path(BHAVCOPY_DIR, date(2023, 4, 10))
    assert str(p).endswith("2023/Apr/20230410_NSEFO.csv")


def test_find_bhavcopy_finds_existing():
    # April 10, 2023 file exists in bhavcopy
    path = _find_bhavcopy(BHAVCOPY_DIR, date(2023, 4, 10))
    assert path is not None
    assert path.exists()


def test_find_bhavcopy_scans_back_over_weekend():
    # April 9 is a Sunday — should scan back and find Friday April 7 or Saturday
    path = _find_bhavcopy(BHAVCOPY_DIR, date(2023, 4, 9))
    assert path is not None


def test_find_bhavcopy_returns_none_for_missing_range():
    path = _find_bhavcopy(BHAVCOPY_DIR, date(2015, 1, 1), max_lookback_days=5)
    assert path is None


# ── contracts_for_expiry ───────────────────────────────────────────────────

def test_contracts_for_expiry_nifty_returns_ce_and_pe():
    # NIFTY April 2023 monthly expiry
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    types = {s.instrument_type for s in specs}
    assert InstrumentType.CE in types
    assert InstrumentType.PE in types


def test_contracts_for_expiry_includes_fut_for_monthly():
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR, include_futures=True)
    types = {s.instrument_type for s in specs}
    assert InstrumentType.FUT in types


def test_contracts_for_expiry_no_fut_when_excluded():
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR, include_futures=False)
    assert all(s.instrument_type != InstrumentType.FUT for s in specs)


def test_contracts_for_expiry_strikes_are_positive():
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    option_specs = [s for s in specs if s.strike is not None]
    assert all(s.strike > 0 for s in option_specs)


def test_contracts_for_expiry_no_duplicate_contracts():
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    keys = [(s.strike, s.instrument_type) for s in specs]
    assert len(keys) == len(set(keys))


def test_contracts_for_expiry_sorted_order():
    specs = contracts_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    # FUT must come before CE/PE
    itypes = [s.instrument_type for s in specs]
    if InstrumentType.FUT in itypes:
        assert itypes[0] == InstrumentType.FUT


def test_contracts_for_expiry_raises_for_unknown_underlying():
    with pytest.raises(BhavCopyNotFoundError):
        contracts_for_expiry("FAKESYM", date(2023, 4, 27), BHAVCOPY_DIR)


def test_contracts_for_expiry_banknifty():
    specs = contracts_for_expiry("BANKNIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    assert len(specs) > 0
    assert all(s.underlying == "BANKNIFTY" for s in specs)


# ── strikes_for_expiry ─────────────────────────────────────────────────────

def test_strikes_for_expiry_sorted():
    strikes = strikes_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    assert strikes == sorted(strikes)


def test_strikes_for_expiry_unique():
    strikes = strikes_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    assert len(strikes) == len(set(strikes))


def test_strikes_for_expiry_reasonable_range():
    strikes = strikes_for_expiry("NIFTY", date(2023, 4, 27), BHAVCOPY_DIR)
    # NIFTY was around 17500 in April 2023; strikes should span a range around that
    assert any(15000 <= s <= 20000 for s in strikes)
