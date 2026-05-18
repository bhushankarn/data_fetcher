from __future__ import annotations

from typing import TYPE_CHECKING

import psycopg2
import psycopg2.extras

if TYPE_CHECKING:
    from data_fetcher.config import Settings


def get_connection(settings: Settings):
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )


def create_futures_table(conn, underlying: str) -> None:
    t = f"{underlying.lower()}_futures"
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {t} (
                id            SERIAL PRIMARY KEY,
                tradingsymbol VARCHAR,
                expiry_date   DATE,
                datetime      TIMESTAMP WITHOUT TIME ZONE,
                open          DOUBLE PRECISION,
                high          DOUBLE PRECISION,
                low           DOUBLE PRECISION,
                close         DOUBLE PRECISION,
                volume        BIGINT,
                oi            BIGINT
            )
        """)
        cur.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {t}_unique_tradingsymbol_datetime
            ON {t} (tradingsymbol, datetime)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{t}_expiry
            ON {t} (expiry_date, datetime DESC)
        """)
    conn.commit()


def upsert_futures(conn, underlying: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    t = f"{underlying.lower()}_futures"
    sql = f"""
        INSERT INTO {t} (tradingsymbol, expiry_date, datetime, open, high, low, close, volume, oi)
        VALUES %s
        ON CONFLICT (tradingsymbol, datetime) DO NOTHING
        RETURNING id
    """
    data = [
        (r["tradingsymbol"], r["expiry_date"], r["datetime"],
         r["open"], r["high"], r["low"], r["close"], r["volume"], r["oi"])
        for r in rows
    ]
    with conn.cursor() as cur:
        result = psycopg2.extras.execute_values(cur, sql, data, fetch=True, page_size=500)
    conn.commit()
    return len(result)


def upsert_options(conn, underlying: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    t = underlying.lower()
    sql = f"""
        INSERT INTO {t} (tradingsymbol, expiry_date, strike, instrument_type,
                         datetime, open, high, low, close, volume, oi)
        VALUES %s
        ON CONFLICT (tradingsymbol, datetime) DO NOTHING
        RETURNING id
    """
    data = [
        (r["tradingsymbol"], r["expiry_date"], r["strike"], r["instrument_type"],
         r["datetime"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["oi"])
        for r in rows
    ]
    with conn.cursor() as cur:
        result = psycopg2.extras.execute_values(cur, sql, data, fetch=True, page_size=500)
    conn.commit()
    return len(result)
