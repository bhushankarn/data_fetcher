from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from data_fetcher.models import ContractSpec, OHLCVCandle

COLUMNS = ["date", "open", "high", "low", "close", "volume", "oi"]
DATE_FMT = "%Y-%m-%d %H:%M:%S"


def output_path(spec: ContractSpec, tradingsymbol: str, output_dir: Path) -> Path:
    """Build output file path: output_dir/underlying/YYYY-MM-DD/tradingsymbol.csv"""
    expiry_str = spec.expiry.strftime("%Y-%m-%d")
    return output_dir / spec.underlying / expiry_str / f"{tradingsymbol}.csv"


def file_exists(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def write_candles(
    candles: list[OHLCVCandle],
    path: Path,
    overwrite: bool = False,
) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; use overwrite=True to replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "date": c.date.strftime(DATE_FMT),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "oi": c.oi,
        }
        for c in sorted(candles, key=lambda x: x.date)
    ]
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
