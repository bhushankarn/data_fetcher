from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_fetcher.models import ContractSpec, OHLCVCandle


class SourceAuthError(Exception):
    pass


class SourceFetchError(Exception):
    pass


class ContractNotFoundError(Exception):
    pass


class ContractExpiredError(Exception):
    pass


class DataSource(ABC):
    name: str  # class-level constant, e.g. "kite" or "breeze"

    @abstractmethod
    def connect(self) -> None:
        """Authenticate and initialise the SDK client. Raises SourceAuthError on failure."""
        ...

    @abstractmethod
    def fetch(
        self,
        spec: ContractSpec,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[OHLCVCandle]:
        """
        Fetch 1-min candles for [from_dt, to_dt]. Handles chunking, rate limiting,
        and retries internally. Returns time-sorted, deduplicated OHLCVCandle list.
        """
        ...

    @abstractmethod
    def supports_expired(self) -> bool:
        """True if this source can serve data for expired contracts."""
        ...
