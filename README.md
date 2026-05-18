# data-fetcher

NSE derivatives 1-minute OHLCV+OI data fetcher. Supports ICICI Breeze and Zerodha Kite Connect as data sources. Outputs CSV files per contract and optionally syncs to PostgreSQL.

## Requirements

- Python 3.9+
- ICICI Breeze and/or Zerodha Kite Connect API credentials

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `KITE_API_KEY` / `KITE_API_SECRET` / `KITE_ACCESS_TOKEN` | Zerodha Kite credentials (access token regenerated daily) |
| `BREEZE_API_KEY` / `BREEZE_API_SECRET` / `BREEZE_SESSION_TOKEN` | ICICI Breeze credentials |
| `OUTPUT_DIR` | Directory for CSV output (default: `./output`) |
| `DEFAULT_SOURCE` | `kite` \| `breeze` \| `auto` (default: `auto`) |
| `DAYS_BEFORE_EXPIRY` | Fetch window per contract in days before expiry (default: `30`) |
| `OVERWRITE` | Overwrite existing CSVs (default: `false`) |
| `UNDERLYINGS` | Default symbols for bulk fetch, JSON array (default: `["NIFTY","BANKNIFTY"]`) |
| `BHAVCOPY_DIR` | Path to NSE F&O bhavcopy CSVs — required for `fetch-expiry` and `--all-strikes` |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL connection (for `db-init` / `db-sync`) |

### Breeze session token

The ICICI Breeze session token must be refreshed each day. Use the helper script:

```bash
python gen_breeze_token.py
```

This opens the ICICI Direct login page, prompts you to paste the redirect URL or token, verifies it against the API, and writes `BREEZE_SESSION_TOKEN` back into `.env`.

---

## CLI reference

All commands are available via the `data-fetcher` entry point.

```
data-fetcher --help
```

---

### `fetch-contract`

Fetch 1-min OHLCV+OI data for a **single** derivative contract.

```
data-fetcher fetch-contract SYMBOL EXPIRY INSTRUMENT_TYPE [OPTIONS]
```

| Argument / Option | Description |
|---|---|
| `SYMBOL` | Underlying symbol, e.g. `NIFTY` |
| `EXPIRY` | Expiry date `YYYY-MM-DD` |
| `INSTRUMENT_TYPE` | `FUT` \| `CE` \| `PE` |
| `--strike`, `-s` | Strike price — required for `CE`/`PE` |
| `--source` | Override source: `kite` \| `breeze` \| `auto` |
| `--overwrite` | Overwrite existing CSV |
| `--output-dir`, `-o` | Override output directory |
| `--days-before-expiry`, `-d` | Override fetch window (days before expiry) |

**Examples:**

```bash
# NIFTY futures expiring 2025-01-30
data-fetcher fetch-contract NIFTY 2025-01-30 FUT

# NIFTY 24000 CE expiring 2025-01-30
data-fetcher fetch-contract NIFTY 2025-01-30 CE --strike 24000

# Force Breeze, overwrite existing file
data-fetcher fetch-contract BANKNIFTY 2025-01-30 PE --strike 52000 --source breeze --overwrite
```

---

### `fetch-expiry`

Fetch **all contracts** for a single underlying + expiry. Strikes are enumerated from bhavcopy CSVs (`BHAVCOPY_DIR`).

```
data-fetcher fetch-expiry SYMBOL EXPIRY [OPTIONS]
```

| Option | Description |
|---|---|
| `--type` | Instrument types to fetch (repeat for multiple; default: `FUT CE PE`) |
| `--no-futures` | Exclude futures contracts |
| `--source` | `kite` \| `breeze` \| `auto` |
| `--overwrite` | Overwrite existing CSVs |
| `--output-dir`, `-o` | Override output directory |
| `--days-before-expiry`, `-d` | Override fetch window |
| `--bhavcopy-dir` | Override `BHAVCOPY_DIR` from `.env` |

**Examples:**

```bash
# All contracts for NIFTY expiring 2025-01-30
data-fetcher fetch-expiry NIFTY 2025-01-30

# Options only (no futures)
data-fetcher fetch-expiry NIFTY 2025-01-30 --type CE --type PE --no-futures
```

---

### `fetch-bulk`

Fetch data for **multiple underlyings across a range of expiries**.

```
data-fetcher fetch-bulk --underlying SYMBOL --expiry-from DATE --expiry-to DATE [OPTIONS]
```

| Option | Description |
|---|---|
| `--underlying`, `-u` | Underlying symbol (repeat for multiple) — **required** |
| `--expiry-from` | Start of expiry date range `YYYY-MM-DD` — **required** |
| `--expiry-to` | End of expiry date range `YYYY-MM-DD` — **required** |
| `--type` | Instrument types (repeat; default: `FUT CE PE`) |
| `--strike`, `-s` | Strike price (repeat for multiple; ignored for FUT) |
| `--all-strikes` | Enumerate all strikes from bhavcopy (requires `BHAVCOPY_DIR`) |
| `--no-weekly` | Fetch monthly expiries only |
| `--source` | `kite` \| `breeze` \| `auto` |
| `--overwrite` | Overwrite existing CSVs |
| `--output-dir`, `-o` | Override output directory |
| `--days-before-expiry`, `-d` | Override fetch window |
| `--bhavcopy-dir` | Override `BHAVCOPY_DIR` from `.env` |

**Examples:**

```bash
# NIFTY + BANKNIFTY futures for all expiries in Jan 2025
data-fetcher fetch-bulk \
  --underlying NIFTY --underlying BANKNIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-01-31 \
  --type FUT

# NIFTY options at specific strikes, monthly expiries only
data-fetcher fetch-bulk \
  --underlying NIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-06-30 \
  --type CE --type PE \
  --strike 23000 --strike 24000 --strike 25000 \
  --no-weekly

# All strikes from bhavcopy for NIFTY + BANKNIFTY
data-fetcher fetch-bulk \
  --underlying NIFTY --underlying BANKNIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-03-31 \
  --all-strikes
```

---

### `db-init`

Create futures tables in PostgreSQL (idempotent — safe to re-run).

```
data-fetcher db-init [OPTIONS]
```

| Option | Description |
|---|---|
| `--underlying`, `-u` | Create table for specific underlying (repeat; default: all found in `output/`) |
| `--output-dir`, `-o` | Override output directory used to discover underlyings |

**Examples:**

```bash
# Create tables for all underlyings found in output/
data-fetcher db-init

# Create tables for specific underlyings
data-fetcher db-init --underlying NIFTY --underlying BANKNIFTY
```

---

### `db-sync`

Scan the `output/` directory and upsert CSV data into the database.

```
data-fetcher db-sync [OPTIONS]
```

| Option | Description |
|---|---|
| `--underlying`, `-u` | Filter to specific underlying (repeat; default: all) |
| `--type`, `-t` | Instrument type to sync: `FUT` \| `CE` \| `PE` (repeat; default: all) |
| `--expiry`, `-e` | Filter to a single expiry `YYYY-MM-DD` |
| `--output-dir`, `-o` | Override output directory |

**Examples:**

```bash
# Sync everything
data-fetcher db-sync

# Sync only NIFTY futures
data-fetcher db-sync --underlying NIFTY --type FUT

# Sync a specific expiry
data-fetcher db-sync --expiry 2025-01-30
```

---

### `generate-symbol`

Dry-run: print the NSE tradingsymbol that would be generated for a contract (no API calls).

```
data-fetcher generate-symbol SYMBOL EXPIRY INSTRUMENT_TYPE [OPTIONS]
```

| Option | Description |
|---|---|
| `--strike`, `-s` | Strike price (required for CE/PE) |

**Example:**

```bash
data-fetcher generate-symbol NIFTY 2025-01-30 CE --strike 24000
```

---

## Output format

CSVs are written to `{OUTPUT_DIR}/{UNDERLYING}/{tradingsymbol}.csv` with columns:

```
datetime, open, high, low, close, volume, oi
```

---

## Running tests

```bash
pytest
```

---

## Examples

### First-time setup

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure credentials
cp .env.example .env
# Edit .env — fill in BREEZE_API_KEY, BREEZE_API_SECRET

# 3. Get today's Breeze session token (do this every morning)
python gen_breeze_token.py

# 4. Verify the symbol generator works (no API calls needed)
data-fetcher generate-symbol NIFTY 2025-01-30 FUT
# → NIFTY25JANFUT
data-fetcher generate-symbol NIFTY 2025-01-30 CE --strike 24000
# → NIFTY25JAN24000CE
```

---

### Fetch a single contract

```bash
# Current-month NIFTY futures
data-fetcher fetch-contract NIFTY 2025-01-30 FUT

# ATM call option
data-fetcher fetch-contract NIFTY 2025-01-30 CE --strike 24000

# Re-fetch even if the CSV already exists
data-fetcher fetch-contract NIFTY 2025-01-30 CE --strike 24000 --overwrite

# Save to a custom directory
data-fetcher fetch-contract BANKNIFTY 2025-01-30 FUT --output-dir /data/derivatives

# Fetch only the last 7 days before expiry (shorter window)
data-fetcher fetch-contract NIFTY 2025-01-30 FUT --days-before-expiry 7
```

---

### Fetch all strikes for one expiry (requires BHAVCOPY_DIR)

```bash
# All NIFTY contracts (FUT + all CE/PE strikes) for Jan 2025 expiry
data-fetcher fetch-expiry NIFTY 2025-01-30

# Options only — skip the futures contract
data-fetcher fetch-expiry NIFTY 2025-01-30 --type CE --type PE --no-futures

# Override bhavcopy path inline
data-fetcher fetch-expiry NIFTY 2025-01-30 --bhavcopy-dir /data/bhavcopy
```

---

### Bulk fetch across a date range

```bash
# NIFTY + BANKNIFTY futures for all of 2024
# (futures are monthly-only; weekly expiries are skipped automatically)
data-fetcher fetch-bulk \
  --underlying NIFTY --underlying BANKNIFTY \
  --expiry-from 2024-01-01 --expiry-to 2024-12-31 \
  --type FUT

# NIFTY options at ATM ± 2 strikes for Q1 2025, weekly + monthly expiries
data-fetcher fetch-bulk \
  --underlying NIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-03-31 \
  --type CE --type PE \
  --strike 23500 --strike 24000 --strike 24500

# Monthly expiries only (skip weekly)
data-fetcher fetch-bulk \
  --underlying NIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-06-30 \
  --type CE --type PE \
  --strike 24000 \
  --no-weekly

# All strikes from bhavcopy, skip files already on disk
data-fetcher fetch-bulk \
  --underlying NIFTY --underlying BANKNIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-03-31 \
  --all-strikes

# Same but force re-download everything
data-fetcher fetch-bulk \
  --underlying NIFTY \
  --expiry-from 2025-01-01 --expiry-to 2025-03-31 \
  --all-strikes --overwrite
```

---

### Database workflow

```bash
# 1. Create tables (run once per underlying, or whenever you add a new one)
data-fetcher db-init --underlying NIFTY --underlying BANKNIFTY

# 2. Sync all CSVs in output/ into the database
data-fetcher db-sync

# 3. Sync only NIFTY futures (faster if you only fetched futures)
data-fetcher db-sync --underlying NIFTY --type FUT

# 4. Sync a specific expiry after a fresh fetch
data-fetcher db-sync --expiry 2025-01-30

# 5. Sync from a non-default output directory
data-fetcher db-sync --output-dir /data/derivatives
```

---

### Typical daily workflow (Breeze)

```bash
# Morning: refresh session token
python gen_breeze_token.py

# Fetch today's active weekly NIFTY contracts (options + futures)
data-fetcher fetch-expiry NIFTY 2025-01-09

# Sync new data into the database
data-fetcher db-sync --underlying NIFTY --expiry 2025-01-09
```
