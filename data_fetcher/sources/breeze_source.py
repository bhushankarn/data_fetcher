from __future__ import annotations

import time
from collections import deque
from datetime import datetime, date as date_type
from typing import Optional

import structlog
from tenacity import retry, wait_exponential, stop_after_attempt

from data_fetcher.config import Settings
from data_fetcher.digestors.breeze_digestor import BreezeDigestor
from data_fetcher.models import ContractSpec, InstrumentType, OHLCVCandle
from data_fetcher.sources.base import DataSource, SourceAuthError, SourceFetchError

log = structlog.get_logger()

# Breeze API quirk: from_date/to_date use IST formatted with Z suffix
_DT_FMT = "%Y-%m-%dT%H:%M:%S.000Z"


class BreezeSource(DataSource):
    name = "breeze"

    _RATE_LIMIT = 100   # calls per minute
    _RATE_WINDOW = 60.0
    _DAILY_LIMIT = 5000
    _DAILY_WARN = 4900

    def __init__(self, settings: Settings, digestor: Optional[BreezeDigestor] = None):
        self._settings = settings
        self._digestor = digestor or BreezeDigestor()
        self._breeze = None
        self._call_times: deque[float] = deque()
        self._daily_calls: int = 0

    def connect(self) -> None:
        if not self._settings.breeze_api_key or not self._settings.breeze_session_token:
            raise SourceAuthError(
                "BREEZE_API_KEY and BREEZE_SESSION_TOKEN must be set in .env"
            )
        try:
            from breeze_connect import BreezeConnect
        except ImportError:
            raise SourceAuthError("breeze-connect package not installed: pip install breeze-connect")
        self._breeze = BreezeConnect(api_key=self._settings.breeze_api_key)
        self._breeze.generate_session(
            api_secret=self._settings.breeze_api_secret,
            session_token=self._settings.breeze_session_token,
        )
        log.info("breeze_connected")

    def _rate_limit_wait(self) -> None:
        if self._daily_calls >= self._DAILY_LIMIT:
            raise SourceFetchError("Breeze daily API call limit (5000) reached")
        if self._daily_calls >= self._DAILY_WARN:
            log.warning("breeze_daily_limit_approaching", calls=self._daily_calls)

        now = time.monotonic()
        while self._call_times and now - self._call_times[0] > self._RATE_WINDOW:
            self._call_times.popleft()
        if len(self._call_times) >= self._RATE_LIMIT:
            sleep_for = self._RATE_WINDOW - (now - self._call_times[0]) + 0.1
            time.sleep(max(0.0, sleep_for))

        self._call_times.append(time.monotonic())
        self._daily_calls += 1

    @staticmethod
    def _expiry_param(expiry: date_type) -> str:
        return f"{expiry.strftime('%Y-%m-%d')}T06:00:00.000Z"

    @staticmethod
    def _map_right(instrument_type: InstrumentType) -> str:
        if instrument_type == InstrumentType.FUT:
            return "others"
        elif instrument_type == InstrumentType.CE:
            return "call"
        else:
            return "put"

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _fetch_raw(
        self,
        stock_code: str,
        expiry_date: str,
        strike_price: str,
        right: str,
        product_type: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> dict:
        self._rate_limit_wait()
        return self._breeze.get_historical_data_v2(
            interval="1minute",
            from_date=from_dt.strftime(_DT_FMT),
            to_date=to_dt.strftime(_DT_FMT),
            stock_code=stock_code,
            exchange_code="NFO",
            product_type=product_type,
            expiry_date=expiry_date,
            right=right,
            strike_price=strike_price,
        )

    def fetch(
        self,
        spec: ContractSpec,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[OHLCVCandle]:
        if self._breeze is None:
            raise SourceAuthError("call connect() before fetch()")

        from data_fetcher.nse_utils import generate_tradingsymbol
        raw = self._fetch_raw(
            stock_code=spec.underlying,
            expiry_date=self._expiry_param(spec.expiry),
            strike_price="" if spec.is_future else _fmt_strike(spec.strike),
            right=self._map_right(spec.instrument_type),
            product_type="futures" if spec.is_future else "options",
            from_dt=from_dt,
            to_dt=to_dt,
        )
        candles = self._digestor.digest(raw)
        log.debug("breeze_fetched", symbol=generate_tradingsymbol(spec), candles=len(candles))
        return sorted(candles, key=lambda c: c.date)

    def supports_expired(self) -> bool:
        return True


def _fmt_strike(strike: Optional[float]) -> str:
    if strike is None:
        return ""
    if strike == int(strike):
        return str(int(strike))
    return str(strike)
