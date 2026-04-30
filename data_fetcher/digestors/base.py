from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_fetcher.models import OHLCVCandle


class Digestor(ABC):
    """Converts raw API response for one chunk into a list of OHLCVCandle. Stateless."""

    @abstractmethod
    def digest(self, raw: object) -> list[OHLCVCandle]: ...
