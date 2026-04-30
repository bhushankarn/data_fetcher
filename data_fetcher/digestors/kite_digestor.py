from __future__ import annotations

from datetime import datetime

from data_fetcher.digestors.base import Digestor
from data_fetcher.models import OHLCVCandle


class KiteDigestor(Digestor):
    """
    Converts pykiteconnect historical_data(oi=True) response to OHLCVCandle list.
    Input: list of dicts with keys date, open, high, low, close, volume, oi.
    """

    def digest(self, raw: object) -> list[OHLCVCandle]:
        if not isinstance(raw, list):
            return []
        candles = []
        for row in raw:
            dt = row["date"]
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt)
            candles.append(OHLCVCandle(
                date=dt.replace(second=0, microsecond=0),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                oi=int(row.get("oi") or 0),
            ))
        return candles
