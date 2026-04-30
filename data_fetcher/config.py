from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Kite Connect
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    # ICICI Breeze
    breeze_api_key: str = ""
    breeze_api_secret: str = ""
    breeze_session_token: str = ""

    # Output
    output_dir: Path = Path("output")

    # Fetch behaviour
    default_source: Literal["kite", "breeze", "auto"] = "auto"
    days_before_expiry: int = 30
    overwrite: bool = False
    underlyings: list[str] = Field(default=["NIFTY", "BANKNIFTY"])

    # Instruments cache (Kite instruments CSV cached daily)
    kite_instruments_cache_dir: Path = Path.home() / ".cache" / "data_fetcher"

    # NSE F&O bhavcopy directory for strike enumeration (used by fetch-expiry / --all-strikes)
    # Structure: {bhavcopy_dir}/{YYYY}/{Mon}/{YYYYMMDD}_NSEFO.csv
    bhavcopy_dir: Optional[Path] = None

