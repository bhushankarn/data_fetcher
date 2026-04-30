import csv
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from data_fetcher.csv_writer import COLUMNS, file_exists, output_path, write_candles
from data_fetcher.models import ContractSpec, InstrumentType, OHLCVCandle


def _make_spec() -> ContractSpec:
    return ContractSpec(
        underlying="NIFTY",
        expiry=date(2025, 4, 17),
        instrument_type=InstrumentType.CE,
        strike=18000.0,
    )


def _make_candles() -> list[OHLCVCandle]:
    return [
        OHLCVCandle(datetime(2025, 4, 17, 9, 15), 100.0, 102.0, 99.0, 101.0, 5000.0, 10000),
        OHLCVCandle(datetime(2025, 4, 17, 9, 16), 101.0, 103.0, 100.0, 102.0, 3000.0, 10500),
    ]


def test_write_candles_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path, overwrite=False)
        assert path.exists()


def test_write_candles_columns():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path)
        with open(path) as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == COLUMNS


def test_write_candles_row_values():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["date"] == "2025-04-17 09:15:00"
        assert float(rows[0]["open"]) == 100.0
        assert float(rows[0]["oi"]) == 10000.0


def test_write_candles_sorted_by_date():
    candles = list(reversed(_make_candles()))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(candles, path)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["date"] < rows[1]["date"]


def test_write_empty_candles_writes_header_only():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles([], path)
        with open(path) as f:
            content = f.read()
        assert "date,open,high,low,close,volume,oi" in content


def test_file_exists_false_for_missing():
    assert file_exists(Path("/tmp/definitely_does_not_exist_xyz.csv")) is False


def test_file_exists_true_for_written():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path)
        assert file_exists(path) is True


def test_overwrite_raises_when_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path)
        with pytest.raises(FileExistsError):
            write_candles(_make_candles(), path, overwrite=False)


def test_overwrite_true_replaces_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.csv"
        write_candles(_make_candles(), path)
        write_candles([], path, overwrite=True)
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert rows == []


def test_output_path_structure():
    spec = _make_spec()
    p = output_path(spec, "NIFTY2541718000CE", Path("/data"))
    assert str(p) == "/data/NIFTY/2025-04-17/NIFTY2541718000CE.csv"


def test_write_candles_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "NIFTY" / "2025-04-17" / "NIFTY2541718000CE.csv"
        write_candles(_make_candles(), path)
        assert path.exists()
