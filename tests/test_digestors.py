from datetime import datetime

from data_fetcher.digestors.breeze_digestor import BreezeDigestor
from data_fetcher.digestors.kite_digestor import KiteDigestor


# ── KiteDigestor ───────────────────────────────────────────────────────────

KITE_RAW = [
    {"date": datetime(2025, 4, 17, 9, 15), "open": 100.0, "high": 102.0,
     "low": 99.0, "close": 101.0, "volume": 5000, "oi": 12000},
    {"date": datetime(2025, 4, 17, 9, 16), "open": 101.0, "high": 103.0,
     "low": 100.0, "close": 102.0, "volume": 3000, "oi": 12500},
]


def test_kite_digest_basic():
    candles = KiteDigestor().digest(KITE_RAW)
    assert len(candles) == 2
    assert candles[0].date == datetime(2025, 4, 17, 9, 15)
    assert candles[0].open == 100.0
    assert candles[0].close == 101.0
    assert candles[0].volume == 5000.0


def test_kite_oi_populated():
    candles = KiteDigestor().digest(KITE_RAW)
    assert candles[0].oi == 12000
    assert candles[1].oi == 12500
    assert isinstance(candles[0].oi, int)


def test_kite_oi_missing_defaults_to_zero():
    raw = [{"date": datetime(2025, 4, 17, 9, 15), "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 1000}]
    candles = KiteDigestor().digest(raw)
    assert candles[0].oi == 0


def test_kite_empty_input():
    assert KiteDigestor().digest([]) == []


def test_kite_non_list_input():
    assert KiteDigestor().digest(None) == []


def test_kite_date_as_string():
    raw = [{"date": "2025-04-17T09:15:00", "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 1000}]
    candles = KiteDigestor().digest(raw)
    assert len(candles) == 1
    assert candles[0].date == datetime(2025, 4, 17, 9, 15)


# ── BreezeDigestor ─────────────────────────────────────────────────────────

BREEZE_RAW = {
    "Status": 200,
    "Error": None,
    "Success": [
        {"datetime": "2025-04-17 09:15:00", "open": "200.0", "high": "205.0",
         "low": "198.0", "close": "203.0", "volume": "2000", "open_interest": "50000"},
        {"datetime": "2025-04-17 09:16:00", "open": "203.0", "high": "207.0",
         "low": "202.0", "close": "206.0", "volume": "1500", "open_interest": "51000"},
    ],
}


def test_breeze_digest_basic():
    candles = BreezeDigestor().digest(BREEZE_RAW)
    assert len(candles) == 2
    assert candles[0].date == datetime(2025, 4, 17, 9, 15)
    assert candles[0].open == 200.0
    assert candles[0].oi == 50000
    assert isinstance(candles[0].oi, int)


def test_breeze_oi_populated():
    candles = BreezeDigestor().digest(BREEZE_RAW)
    assert candles[1].oi == 51000


def test_breeze_empty_success():
    raw = {"Status": 200, "Error": None, "Success": []}
    assert BreezeDigestor().digest(raw) == []


def test_breeze_error_status():
    raw = {"Status": 500, "Error": "Internal error", "Success": None}
    assert BreezeDigestor().digest(raw) == []


def test_breeze_null_oi_defaults_to_zero():
    raw = {
        "Status": 200, "Error": None,
        "Success": [
            {"datetime": "2025-04-17 09:15:00", "open": "100.0", "high": "101.0",
             "low": "99.0", "close": "100.5", "volume": "500", "open_interest": None},
        ],
    }
    candles = BreezeDigestor().digest(raw)
    assert candles[0].oi == 0
    assert isinstance(candles[0].oi, int)
