from __future__ import annotations

from datetime import datetime

from data_fetcher.digestors.base import Digestor
from data_fetcher.models import OHLCVCandle

_DT_FMT = "%Y-%m-%d %H:%M:%S"


class BreezeDigestor(Digestor):
    """
    Converts breeze-connect get_historical_data_v2() response to OHLCVCandle list.
    Input: {"Status": 200, "Error": None, "Success": [{...}, ...]}
    Each row has: datetime, open, high, low, close, volume, open_interest.
    """

    def digest(self, raw: object) -> list[OHLCVCandle]:
        if not isinstance(raw, dict) or raw.get("Status") != 200:
            return []
        rows = raw.get("Success") or []
        candles = []
        for row in rows:
            dt = datetime.strptime(row["datetime"], _DT_FMT)
            candles.append(OHLCVCandle(
                date=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                oi=int(float(row.get("open_interest") or 0)),
            ))
        return candles
