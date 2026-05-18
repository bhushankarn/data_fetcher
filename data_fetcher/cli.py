from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

import structlog
import typer

from data_fetcher.config import Settings
from data_fetcher.db import create_futures_table, get_connection
from data_fetcher.db_sync import sync_output
from data_fetcher.models import ContractSpec, InstrumentType
from data_fetcher.nse_utils import generate_tradingsymbol
from data_fetcher.runner import FetchRunner

app = typer.Typer(
    name="data-fetcher",
    help="NSE derivatives 1-min OHLCV+OI data fetcher.",
    no_args_is_help=True,
)


def _setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def _load_settings(
    source: Optional[str],
    output_dir: Optional[Path],
    overwrite: bool,
    days_before_expiry: Optional[int],
) -> Settings:
    s = Settings()
    if source is not None:
        object.__setattr__(s, "default_source", source)
    if output_dir is not None:
        object.__setattr__(s, "output_dir", output_dir)
    if overwrite:
        object.__setattr__(s, "overwrite", True)
    if days_before_expiry is not None:
        object.__setattr__(s, "days_before_expiry", days_before_expiry)
    return s


@app.command("fetch-contract")
def fetch_contract(
    symbol: str = typer.Argument(..., help="Underlying symbol, e.g. NIFTY"),
    expiry: str = typer.Argument(..., help="Expiry date YYYY-MM-DD"),
    instrument_type: str = typer.Argument(..., help="FUT | CE | PE"),
    strike: Optional[float] = typer.Option(None, "--strike", "-s", help="Strike price (required for CE/PE)"),
    source: Optional[str] = typer.Option(None, "--source", help="kite | breeze | auto"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing CSV"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
    days_before_expiry: Optional[int] = typer.Option(None, "--days-before-expiry", "-d"),
) -> None:
    """Fetch 1-min OHLCV+OI data for a single derivative contract."""
    _setup_logging()
    itype = InstrumentType(instrument_type.upper())
    if itype != InstrumentType.FUT and strike is None:
        typer.echo("ERROR: --strike is required for CE/PE contracts", err=True)
        raise typer.Exit(1)

    spec = ContractSpec(
        underlying=symbol.upper(),
        expiry=date.fromisoformat(expiry),
        instrument_type=itype,
        strike=strike,
    )
    settings = _load_settings(source, output_dir, overwrite, days_before_expiry)
    runner = FetchRunner(settings)
    result = runner.fetch_contract(spec, overwrite=overwrite)

    if result.error:
        typer.echo(f"ERROR: {result.error}", err=True)
        raise typer.Exit(1)
    elif result.skipped:
        typer.echo(f"Skipped (already exists): {result.output_path}")
    else:
        typer.echo(f"Saved {len(result.candles)} candles → {result.output_path}")


@app.command("fetch-expiry")
def fetch_expiry(
    symbol: str = typer.Argument(..., help="Underlying symbol, e.g. NIFTY"),
    expiry: str = typer.Argument(..., help="Expiry date YYYY-MM-DD"),
    instrument_types: List[str] = typer.Option(["FUT", "CE", "PE"], "--type", help="FUT | CE | PE (repeat for multiple)"),
    no_futures: bool = typer.Option(False, "--no-futures", help="Exclude FUT contracts"),
    source: Optional[str] = typer.Option(None, "--source"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
    days_before_expiry: Optional[int] = typer.Option(None, "--days-before-expiry", "-d"),
    bhavcopy_dir: Optional[Path] = typer.Option(None, "--bhavcopy-dir",
                                                  help="Override BHAVCOPY_DIR from .env"),
) -> None:
    """Fetch all contracts for a single underlying + expiry (strikes from bhavcopy)."""
    _setup_logging()
    settings = _load_settings(source, output_dir, overwrite, days_before_expiry)
    if bhavcopy_dir is not None:
        object.__setattr__(settings, "bhavcopy_dir", bhavcopy_dir)

    runner = FetchRunner(settings)
    results = runner.fetch_expiry(
        underlying=symbol.upper(),
        expiry=date.fromisoformat(expiry),
        instrument_types=[t.upper() for t in instrument_types],
        overwrite=overwrite,
        include_futures=not no_futures,
    )
    _print_bulk_summary(results)


@app.command("fetch-bulk")
def fetch_bulk(
    underlyings: List[str] = typer.Option(..., "--underlying", "-u", help="Underlying symbol (repeat for multiple)"),
    expiry_from: str = typer.Option(..., "--expiry-from", help="Start of expiry range YYYY-MM-DD"),
    expiry_to: str = typer.Option(..., "--expiry-to", help="End of expiry range YYYY-MM-DD"),
    instrument_types: List[str] = typer.Option(["FUT", "CE", "PE"], "--type", help="FUT | CE | PE (repeat for multiple)"),
    strikes: List[float] = typer.Option([], "--strike", "-s", help="Strike price (repeat for multiple; ignored for FUT)"),
    source: Optional[str] = typer.Option(None, "--source"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
    days_before_expiry: Optional[int] = typer.Option(None, "--days-before-expiry", "-d"),
    no_weekly: bool = typer.Option(False, "--no-weekly", help="Fetch monthly expiries only"),
    all_strikes: bool = typer.Option(False, "--all-strikes",
                                      help="Enumerate strikes from bhavcopy (requires BHAVCOPY_DIR)"),
    bhavcopy_dir: Optional[Path] = typer.Option(None, "--bhavcopy-dir",
                                                  help="Override BHAVCOPY_DIR from .env"),
) -> None:
    """Fetch 1-min OHLCV+OI data for multiple contracts in bulk."""
    _setup_logging()
    if not all_strikes and any(t.upper() in ("CE", "PE") for t in instrument_types) and not strikes:
        typer.echo(
            "ERROR: provide --strike values or use --all-strikes (bhavcopy) for CE/PE contracts",
            err=True,
        )
        raise typer.Exit(1)

    settings = _load_settings(source, output_dir, overwrite, days_before_expiry)
    if bhavcopy_dir is not None:
        object.__setattr__(settings, "bhavcopy_dir", bhavcopy_dir)

    runner = FetchRunner(settings)
    results = runner.fetch_bulk(
        underlyings=[u.upper() for u in underlyings],
        expiry_from=date.fromisoformat(expiry_from),
        expiry_to=date.fromisoformat(expiry_to),
        instrument_types=[t.upper() for t in instrument_types],
        strikes=strikes,
        overwrite=overwrite,
        include_weekly=not no_weekly,
        all_strikes=all_strikes,
    )
    _print_bulk_summary(results)


def _print_bulk_summary(results: list) -> None:
    fetched = [r for r in results if not r.error and not r.skipped]
    skipped = [r for r in results if r.skipped]
    errors = [r for r in results if r.error]
    typer.echo(f"\nDone — {len(fetched)} fetched, {len(skipped)} skipped, {len(errors)} errors")
    for r in errors:
        typer.echo(f"  ERROR {r.tradingsymbol}: {r.error}", err=True)
    if errors:
        raise typer.Exit(1)


@app.command("db-init")
def db_init(
    underlying: List[str] = typer.Option(
        [], "--underlying", "-u",
        help="Underlying symbol to create futures table for (repeat for multiple; default: all found in output/)",
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
) -> None:
    """Create futures tables in the database (idempotent — safe to re-run)."""
    _setup_logging()
    settings = Settings()
    if output_dir is not None:
        object.__setattr__(settings, "output_dir", output_dir)

    root = settings.output_dir
    if underlying:
        targets = [u.upper() for u in underlying]
    else:
        targets = [d.name.upper() for d in sorted(root.iterdir()) if d.is_dir()] if root.is_dir() else []

    if not targets:
        typer.echo("No underlyings found. Pass --underlying or ensure output/ has subdirectories.")
        raise typer.Exit(1)

    conn = get_connection(settings)
    try:
        for u in targets:
            create_futures_table(conn, u)
            typer.echo(f"Created/verified table: {u.lower()}_futures")
    finally:
        conn.close()


@app.command("db-sync")
def db_sync(
    underlying: List[str] = typer.Option(
        [], "--underlying", "-u",
        help="Filter to specific underlying (repeat for multiple; default: all)",
    ),
    types: List[str] = typer.Option(
        [], "--type", "-t",
        help="Instrument type to sync: FUT | CE | PE (repeat for multiple; default: all)",
    ),
    expiry: Optional[str] = typer.Option(None, "--expiry", "-e", help="Filter to single expiry YYYY-MM-DD"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o"),
) -> None:
    """Scan output/ folder and upsert CSV data into the database."""
    _setup_logging()
    settings = Settings()
    if output_dir is not None:
        object.__setattr__(settings, "output_dir", output_dir)

    expiry_date = None
    if expiry:
        from datetime import date as date_type
        expiry_date = date_type.fromisoformat(expiry)

    sync_output(
        settings=settings,
        underlyings=underlying or None,
        types=types or None,
        expiry=expiry_date,
    )


@app.command("generate-symbol")
def generate_symbol(
    symbol: str = typer.Argument(..., help="Underlying, e.g. NIFTY"),
    expiry: str = typer.Argument(..., help="Expiry date YYYY-MM-DD"),
    instrument_type: str = typer.Argument(..., help="FUT | CE | PE"),
    strike: Optional[float] = typer.Option(None, "--strike", "-s"),
) -> None:
    """Dry-run: print the NSE tradingsymbol that would be generated."""
    spec = ContractSpec(
        underlying=symbol.upper(),
        expiry=date.fromisoformat(expiry),
        instrument_type=InstrumentType(instrument_type.upper()),
        strike=strike,
    )
    typer.echo(generate_tradingsymbol(spec))
