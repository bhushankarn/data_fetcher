from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type

from data_fetcher.config import Settings
from data_fetcher.digestors.kite_digestor import KiteDigestor
from data_fetcher.models import ContractSpec, OHLCVCandle
from data_fetcher.sources.base import (
    DataSource,
    SourceAuthError,
    ContractNotFoundError,
    ContractExpiredError,
)

log = structlog.get_logger()


class _DateEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


class KiteSource(DataSource):
    name = "kite"

    _MAX_DAYS_PER_CHUNK = 60
    _MIN_INTERVAL_SECS = 0.34  # ≤ 3 req/sec for historical endpoint

    def __init__(self, settings: Settings, digestor: Optional[KiteDigestor] = None):
        self._settings = settings
        self._digestor = digestor or KiteDigestor()
        self._kite = None
        self._token_map: dict[str, int] = {}  # "NFO:SYMBOL" → instrument_token

    def connect(self) -> None:
        if not self._settings.kite_api_key or not self._settings.kite_access_token:
            raise SourceAuthError("KITE_API_KEY and KITE_ACCESS_TOKEN must be set in .env")
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            raise SourceAuthError("kiteconnect package not installed: pip install kiteconnect")
        self._kite = KiteConnect(api_key=self._settings.kite_api_key)
        self._kite.set_access_token(self._settings.kite_access_token)
        self._load_instruments()
        log.info("kite_connected")

    def _cache_path(self) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        d = self._settings.kite_instruments_cache_dir
        d.mkdir(parents=True, exist_ok=True)
        return d / f"kite_instruments_{today}.json"

    def _load_instruments(self) -> None:
        cache = self._cache_path()
        instruments = None
        if cache.exists():
            try:
                with open(cache) as f:
                    instruments = json.load(f)
                log.info("kite_instruments_cache_hit", path=str(cache))
            except (json.JSONDecodeError, ValueError):
                log.warning("kite_instruments_cache_corrupt_redownloading", path=str(cache))
                cache.unlink(missing_ok=True)

        if instruments is None:
            log.info("kite_instruments_downloading")
            instruments = self._kite.instruments("NFO")
            with open(cache, "w") as f:
                json.dump(instruments, f, cls=_DateEncoder)
            log.info("kite_instruments_cached", count=len(instruments), path=str(cache))

        for inst in instruments:
            key = f"NFO:{inst['tradingsymbol']}"
            self._token_map[key] = inst["instrument_token"]

    def _resolve_token(self, tradingsymbol: str) -> int:
        key = f"NFO:{tradingsymbol}"
        if key not in self._token_map:
            raise ContractNotFoundError(f"Instrument not found in Kite NFO list: {tradingsymbol}")
        return self._token_map[key]

    def _date_chunks(
        self, from_dt: datetime, to_dt: datetime
    ) -> list[tuple[datetime, datetime]]:
        chunks = []
        current = from_dt
        delta = timedelta(days=self._MAX_DAYS_PER_CHUNK)
        while current < to_dt:
            end = min(current + delta, to_dt)
            chunks.append((current, end))
            current = end
        return chunks

    def _fetch_chunk_raw(
        self, instrument_token: int, from_dt: datetime, to_dt: datetime
    ) -> list[dict]:
        try:
            from kiteconnect.exceptions import TokenException, InputException, NetworkException
        except ImportError:
            from kiteconnect import KiteConnect  # noqa — just to surface import error cleanly
            raise

        @retry(
            wait=wait_fixed(self._MIN_INTERVAL_SECS),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        def _call() -> list[dict]:
            try:
                return self._kite.historical_data(
                    instrument_token,
                    from_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    to_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "minute",
                    oi=True,
                )
            except TokenException as e:
                raise SourceAuthError(
                    "Kite access token expired — regenerate via OAuth flow"
                ) from e
            except InputException as e:
                raise ContractNotFoundError(str(e)) from e

        return _call()

    def fetch(
        self,
        spec: ContractSpec,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[OHLCVCandle]:
        if self._kite is None:
            raise SourceAuthError("call connect() before fetch()")

        from datetime import date
        if spec.expiry < date.today():
            raise ContractExpiredError(
                f"Kite does not support expired contracts: {spec.underlying} {spec.expiry}"
            )

        from data_fetcher.nse_utils import generate_tradingsymbol
        tradingsymbol = generate_tradingsymbol(spec)
        token = self._resolve_token(tradingsymbol)

        chunks = self._date_chunks(from_dt, to_dt)
        all_candles: list[OHLCVCandle] = []

        for i, (chunk_start, chunk_end) in enumerate(chunks):
            if i > 0:
                time.sleep(self._MIN_INTERVAL_SECS)
            raw = self._fetch_chunk_raw(token, chunk_start, chunk_end)
            all_candles.extend(self._digestor.digest(raw))
            log.debug("kite_chunk_fetched", symbol=tradingsymbol, candles=len(raw),
                      chunk=f"{chunk_start.date()}..{chunk_end.date()}")

        return _dedup_sort(all_candles)

    def supports_expired(self) -> bool:
        return False


def _dedup_sort(candles: list[OHLCVCandle]) -> list[OHLCVCandle]:
    seen: set[datetime] = set()
    out = []
    for c in candles:
        if c.date not in seen:
            seen.add(c.date)
            out.append(c)
    return sorted(out, key=lambda c: c.date)
