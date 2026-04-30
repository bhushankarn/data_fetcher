from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from data_fetcher.models import ContractSpec, InstrumentType
from data_fetcher.nse_utils import is_monthly_expiry

_MONTH_DIR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


class BhavCopyNotFoundError(Exception):
    pass


def _bhavcopy_path(bhavcopy_dir: Path, d: date) -> Path:
    """Build the expected path for a given date's NSEFO bhavcopy file."""
    return bhavcopy_dir / str(d.year) / _MONTH_DIR[d.month] / f"{d.strftime('%Y%m%d')}_NSEFO.csv"


def _find_bhavcopy(
    bhavcopy_dir: Path,
    target_date: date,
    max_lookback_days: int = 15,
) -> Optional[Path]:
    """
    Search backwards from target_date for the nearest available bhavcopy file.
    Returns None if nothing found within max_lookback_days.
    """
    for offset in range(max_lookback_days + 1):
        path = _bhavcopy_path(bhavcopy_dir, target_date - timedelta(days=offset))
        if path.exists():
            return path
    return None


def contracts_for_expiry(
    underlying: str,
    expiry: date,
    bhavcopy_dir: Path,
    lookback_days: int = 7,
    include_futures: bool = True,
) -> list[ContractSpec]:
    """
    Return all ContractSpec instances for the given underlying and expiry date
    by reading the nearest NSEFO bhavcopy file found `lookback_days` before expiry.

    Using a date before expiry (rather than the expiry date itself) gives a fuller
    strike range — on expiry day only near-ATM strikes remain active.

    Args:
        underlying:     NSE symbol, e.g. "NIFTY", "BANKNIFTY", "RELIANCE"
        expiry:         Expiry date
        bhavcopy_dir:   Root of the bhavcopy directory tree
        lookback_days:  Target = expiry - lookback_days; scans back up to 15 extra days
        include_futures: Whether to include the FUT contract (monthly expiries only)
    """
    target = expiry - timedelta(days=lookback_days)
    path = _find_bhavcopy(bhavcopy_dir, target)
    if path is None:
        raise BhavCopyNotFoundError(
            f"No bhavcopy file found within {lookback_days + 15} days before "
            f"{expiry} in {bhavcopy_dir}"
        )

    expiry_str = expiry.strftime("%Y-%m-%d")
    df = pd.read_csv(path, dtype=str)

    # Filter to the specific underlying + expiry
    mask = (df["SYMBOL"] == underlying) & (df["EXPIRY_DT_FINAL"] == expiry_str)
    df_expiry = df[mask]

    if df_expiry.empty:
        raise BhavCopyNotFoundError(
            f"No contracts found for {underlying} expiry {expiry} in {path.name}"
        )

    specs: list[ContractSpec] = []
    seen: set[tuple[float, InstrumentType]] = set()

    # Options (CE / PE)
    opts = df_expiry[df_expiry["OPTION_TYP"].isin(["CE", "PE"])]
    for _, row in opts.iterrows():
        strike = float(row["STRIKE_PR"])
        itype = InstrumentType(row["OPTION_TYP"])
        key = (strike, itype)
        if key not in seen:
            seen.add(key)
            specs.append(ContractSpec(
                underlying=underlying,
                expiry=expiry,
                instrument_type=itype,
                strike=strike,
            ))

    # Futures (OPTION_TYP == "XX", INSTRUMENT starts with "FUT")
    if include_futures and is_monthly_expiry(expiry):
        futs = df_expiry[
            (df_expiry["OPTION_TYP"] == "XX") &
            (df_expiry["INSTRUMENT"].str.startswith("FUT"))
        ]
        if not futs.empty:
            specs.append(ContractSpec(
                underlying=underlying,
                expiry=expiry,
                instrument_type=InstrumentType.FUT,
                strike=None,
            ))

    # Sort: FUT first, then CE by strike, then PE by strike
    def _sort_key(s: ContractSpec) -> tuple:
        order = {"FUT": 0, "CE": 1, "PE": 2}
        return (order[s.instrument_type.value], s.strike or 0.0)

    return sorted(specs, key=_sort_key)


def strikes_for_expiry(
    underlying: str,
    expiry: date,
    bhavcopy_dir: Path,
    lookback_days: int = 7,
) -> list[float]:
    """Return sorted unique strike prices for the given underlying + expiry."""
    specs = contracts_for_expiry(
        underlying, expiry, bhavcopy_dir,
        lookback_days=lookback_days,
        include_futures=False,
    )
    return sorted({s.strike for s in specs if s.strike is not None})
