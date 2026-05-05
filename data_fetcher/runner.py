from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from tqdm import tqdm

from data_fetcher.config import Settings
from data_fetcher.csv_writer import file_exists, output_path, write_candles
from data_fetcher.models import ContractSpec, FetchResult, InstrumentType
from data_fetcher.nse_utils import expiries_in_range, generate_tradingsymbol, is_monthly_expiry
from data_fetcher.sources.base import DataSource

log = structlog.get_logger()

_MARKET_OPEN = (9, 15)   # IST 09:15
_MARKET_CLOSE = (15, 30) # IST 15:30


class FetchRunner:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._sources: dict[str, DataSource] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_contract(
        self,
        spec: ContractSpec,
        overwrite: Optional[bool] = None,
    ) -> FetchResult:
        """Fetch a single contract. fetch window = [expiry - days_before_expiry, expiry]."""
        if overwrite is None:
            overwrite = self._settings.overwrite

        tradingsymbol = generate_tradingsymbol(spec)
        out_path = output_path(spec, tradingsymbol, self._settings.output_dir)

        if file_exists(out_path) and not overwrite:
            log.info("skipping_existing", path=str(out_path))
            return FetchResult(
                spec=spec, tradingsymbol=tradingsymbol, candles=[],
                source_name="none", output_path=str(out_path), skipped=True,
            )

        from_dt, to_dt = self._date_range(spec)
        source = self._get_source(spec)

        try:
            candles = source.fetch(spec, from_dt, to_dt)
            write_candles(candles, out_path, overwrite=True)
            log.info("fetched", symbol=tradingsymbol, candles=len(candles), source=source.name)
            return FetchResult(
                spec=spec, tradingsymbol=tradingsymbol, candles=candles,
                source_name=source.name, output_path=str(out_path),
            )
        except Exception as exc:
            log.error("fetch_failed", symbol=tradingsymbol, error=str(exc))
            return FetchResult(
                spec=spec, tradingsymbol=tradingsymbol, candles=[],
                source_name=source.name, output_path=str(out_path), error=str(exc),
            )

    def fetch_expiry(
        self,
        underlying: str,
        expiry: date,
        instrument_types: list[str],
        overwrite: Optional[bool] = None,
        include_futures: bool = True,
    ) -> list[FetchResult]:
        """Fetch all contracts for one underlying + expiry using bhavcopy for strike enumeration."""
        specs = self._specs_from_bhavcopy(
            underlying, expiry,
            instrument_types=instrument_types,
            include_futures=include_futures,
        )
        log.info("fetch_expiry_start", underlying=underlying, expiry=expiry, contracts=len(specs))
        results: list[FetchResult] = []
        for spec in tqdm(specs, desc=f"{underlying} {expiry}", unit="contract"):
            results.append(self.fetch_contract(spec, overwrite=overwrite))
        return results

    def fetch_bulk(
        self,
        underlyings: list[str],
        expiry_from: date,
        expiry_to: date,
        instrument_types: list[str],
        strikes: list[float],
        overwrite: Optional[bool] = None,
        include_weekly: bool = True,
        all_strikes: bool = False,
    ) -> list[FetchResult]:
        """Fetch all matching contracts; shows a tqdm progress bar."""
        if all_strikes:
            specs = self._build_specs_from_bhavcopy(
                underlyings, expiry_from, expiry_to,
                instrument_types, include_weekly,
            )
        else:
            specs = self._build_specs(
                underlyings, expiry_from, expiry_to,
                instrument_types, strikes, include_weekly,
            )
        log.info("bulk_fetch_start", contracts=len(specs))
        results: list[FetchResult] = []
        for spec in tqdm(specs, desc="Fetching contracts", unit="contract"):
            results.append(self.fetch_contract(spec, overwrite=overwrite))
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _date_range(self, spec: ContractSpec) -> tuple[datetime, datetime]:
        if spec.underlying == "NIFTY" and not is_monthly_expiry(spec.expiry):
            days = self._settings.days_before_expiry_weekly
        else:
            days = self._settings.days_before_expiry
        from_date = spec.expiry - timedelta(days=days)
        h_open, m_open = _MARKET_OPEN
        h_close, m_close = _MARKET_CLOSE
        from_dt = datetime(from_date.year, from_date.month, from_date.day, h_open, m_open)
        to_dt = datetime(spec.expiry.year, spec.expiry.month, spec.expiry.day, h_close, m_close)
        return from_dt, to_dt

    def _get_source(self, spec: ContractSpec) -> DataSource:
        is_expired = spec.expiry < date.today()
        mode = self._settings.default_source

        if mode == "kite" and not is_expired:
            return self._init_source("kite")

        # "auto" or "breeze" or expired contract → always Breeze
        return self._init_source("breeze")

    def _init_source(self, name: str) -> DataSource:
        if name not in self._sources:
            if name == "kite":
                from data_fetcher.sources.kite_source import KiteSource
                src: DataSource = KiteSource(self._settings)
            else:
                from data_fetcher.sources.breeze_source import BreezeSource
                src = BreezeSource(self._settings)
            src.connect()
            self._sources[name] = src
        return self._sources[name]

    def _require_bhavcopy_dir(self) -> Path:
        if not self._settings.bhavcopy_dir:
            raise ValueError(
                "BHAVCOPY_DIR must be set in .env to use --all-strikes or fetch-expiry"
            )
        return self._settings.bhavcopy_dir

    def _specs_from_bhavcopy(
        self,
        underlying: str,
        expiry: date,
        instrument_types: list[str],
        include_futures: bool = True,
    ) -> list[ContractSpec]:
        from data_fetcher.instruments.bhavcopy import contracts_for_expiry
        itypes_upper = [t.upper() for t in instrument_types]
        inc_fut = include_futures and "FUT" in itypes_upper
        bhavcopy_dir = self._require_bhavcopy_dir()
        all_specs = contracts_for_expiry(
            underlying, expiry, bhavcopy_dir, include_futures=inc_fut,
        )
        return [s for s in all_specs if s.instrument_type.value in itypes_upper]

    def _build_specs_from_bhavcopy(
        self,
        underlyings: list[str],
        expiry_from: date,
        expiry_to: date,
        instrument_types: list[str],
        include_weekly: bool,
    ) -> list[ContractSpec]:
        from data_fetcher.instruments.bhavcopy import contracts_for_expiry, BhavCopyNotFoundError
        bhavcopy_dir = self._require_bhavcopy_dir()
        expiries = expiries_in_range(
            expiry_from, expiry_to,
            include_weekly=include_weekly,
            include_monthly=True,
        )
        itypes_upper = [t.upper() for t in instrument_types]
        inc_fut = "FUT" in itypes_upper
        specs: list[ContractSpec] = []
        for underlying in underlyings:
            for expiry in expiries:
                try:
                    batch = contracts_for_expiry(
                        underlying, expiry, bhavcopy_dir, include_futures=inc_fut,
                    )
                    specs.extend(s for s in batch if s.instrument_type.value in itypes_upper)
                except BhavCopyNotFoundError as exc:
                    log.warning("bhavcopy_not_found", underlying=underlying,
                                expiry=expiry, error=str(exc))
        return specs

    def _build_specs(
        self,
        underlyings: list[str],
        expiry_from: date,
        expiry_to: date,
        instrument_types: list[str],
        strikes: list[float],
        include_weekly: bool,
    ) -> list[ContractSpec]:
        expiries = expiries_in_range(
            expiry_from, expiry_to,
            include_weekly=include_weekly,
            include_monthly=True,
        )
        specs: list[ContractSpec] = []
        for underlying in underlyings:
            for expiry in expiries:
                for itype_str in instrument_types:
                    itype = InstrumentType(itype_str.upper())
                    if itype == InstrumentType.FUT:
                        if not is_monthly_expiry(expiry):
                            continue  # futures are monthly-only on NSE
                        specs.append(ContractSpec(
                            underlying=underlying,
                            expiry=expiry,
                            instrument_type=itype,
                            strike=None,
                        ))
                    else:
                        for strike in strikes:
                            specs.append(ContractSpec(
                                underlying=underlying,
                                expiry=expiry,
                                instrument_type=itype,
                                strike=strike,
                            ))
        return specs
