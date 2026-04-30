from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional


class InstrumentType(str, Enum):
    FUT = "FUT"
    CE = "CE"
    PE = "PE"


@dataclass(frozen=True)
class ContractSpec:
    underlying: str
    expiry: date
    instrument_type: InstrumentType
    strike: Optional[float] = None  # None for FUT

    @property
    def is_future(self) -> bool:
        return self.instrument_type == InstrumentType.FUT


@dataclass(frozen=True)
class OHLCVCandle:
    date: datetime          # timezone-naive IST, minute-aligned
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: int = 0             # 0 when source doesn't provide it


@dataclass
class FetchResult:
    spec: ContractSpec
    tradingsymbol: str
    candles: list[OHLCVCandle]
    source_name: str
    output_path: str
    skipped: bool = False   # True when file existed and overwrite=False
    error: Optional[str] = None
