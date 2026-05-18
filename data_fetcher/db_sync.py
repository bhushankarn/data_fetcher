from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import structlog

from data_fetcher.config import Settings
from data_fetcher.db import get_connection, upsert_futures, upsert_options

log = structlog.get_logger()

# Matches NSE tradingsymbol suffixes to instrument type
_FUT_RE = re.compile(r"FUT$")
_CE_RE = re.compile(r"\d+CE$")
_PE_RE = re.compile(r"\d+PE$")


def _instrument_type(stem: str) -> Optional[str]:
    if _FUT_RE.search(stem):
        return "FUT"
    if _CE_RE.search(stem):
        return "CE"
    if _PE_RE.search(stem):
        return "PE"
    return None


def _strike_from_symbol(stem: str) -> Optional[float]:
    """Extract strike price from an options tradingsymbol, e.g. NIFTY2642820100CE → 20100.0"""
    m = re.search(r"(\d+)(CE|PE)$", stem)
    if m:
        return float(m.group(1))
    return None


def sync_output(
    settings: Settings,
    output_dir: Optional[Path] = None,
    underlyings: Optional[list[str]] = None,
    types: Optional[list[str]] = None,
    expiry: Optional[date] = None,
) -> None:
    """Scan output/ directory and upsert CSV data into the database.

    Args:
        output_dir: Root output directory (defaults to settings.output_dir).
        underlyings: Filter to these underlying symbols (None = all).
        types: Filter to these instrument types: FUT, CE, PE (None = all).
        expiry: Filter to a single expiry date (None = all).
    """
    root = output_dir or settings.output_dir
    types_upper = {t.upper() for t in types} if types else {"FUT", "CE", "PE"}

    conn = get_connection(settings)
    try:
        total_files = 0
        total_rows = 0

        underlying_dirs = sorted(root.iterdir()) if root.is_dir() else []
        for u_dir in underlying_dirs:
            if not u_dir.is_dir():
                continue
            underlying = u_dir.name.upper()
            if underlyings and underlying not in {u.upper() for u in underlyings}:
                continue

            for expiry_dir in sorted(u_dir.iterdir()):
                if not expiry_dir.is_dir():
                    continue
                try:
                    expiry_date = date.fromisoformat(expiry_dir.name)
                except ValueError:
                    continue
                if expiry and expiry_date != expiry:
                    continue

                for csv_file in sorted(expiry_dir.glob("*.csv")):
                    stem = csv_file.stem
                    itype = _instrument_type(stem)
                    if itype is None or itype not in types_upper:
                        continue

                    try:
                        df = pd.read_csv(csv_file, parse_dates=["date"])
                    except Exception as e:
                        log.warning("skipping unreadable file", file=str(csv_file), error=str(e))
                        continue

                    if df.empty:
                        continue

                    df = df.rename(columns={"date": "datetime"})
                    df["tradingsymbol"] = stem
                    df["expiry_date"] = expiry_date
                    rows = df.to_dict("records")

                    if itype == "FUT":
                        n = upsert_futures(conn, underlying, rows)
                    else:
                        strike = _strike_from_symbol(stem)
                        for r in rows:
                            r["strike"] = strike
                            r["instrument_type"] = itype
                        n = upsert_options(conn, underlying, rows)

                    log.info("synced", file=csv_file.name, underlying=underlying, rows=n)
                    total_files += 1
                    total_rows += n

        log.info("sync complete", files=total_files, rows=total_rows)
        print(f"\nDone — {total_files} files processed, {total_rows} rows upserted")
    finally:
        conn.close()
