from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from src.config import RAW_DATA_DIR, SQL_DIR


TABLE_FILES = [
    ("dim_customers", "dim_customers.csv", ["signup_date"]),
    ("dim_stores", "dim_stores.csv", ["opened_date"]),
    ("dim_products", "dim_products.csv", []),
    ("fact_orders", "fact_orders.csv", ["order_ts", "delivery_ts"]),
    ("fact_order_items", "fact_order_items.csv", []),
    ("fact_sessions", "fact_sessions.csv", ["session_ts"]),
    ("fact_inventory_daily", "fact_inventory_daily.csv", ["inventory_date"]),
    ("fact_marketing_spend", "fact_marketing_spend.csv", ["spend_date"]),
]


def _run_sql_file(connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    connection.exec_driver_sql(sql)


def load_bundle(data_dir: Path, database_url: str, chunk_size: int = 50_000) -> dict:
    engine = create_engine(database_url, future=True)
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        _run_sql_file(connection, SQL_DIR / "00_schema.sql")

    for table, filename, date_columns in TABLE_FILES:
        total = 0
        path = Path(data_dir) / filename
        for chunk in pd.read_csv(path, parse_dates=date_columns or None, chunksize=chunk_size):
            chunk.to_sql(
                table,
                engine,
                schema="qcommerce",
                if_exists="append",
                index=False,
                method="multi",
                chunksize=2_000,
            )
            total += len(chunk)
        counts[table] = total
        print(f"Loaded {table}: {total:,} rows")

    with engine.begin() as connection:
        _run_sql_file(connection, SQL_DIR / "01_views.sql")
        _run_sql_file(connection, SQL_DIR / "02_indexes.sql")
        for table, expected in counts.items():
            actual = connection.execute(text(f"SELECT COUNT(*) FROM qcommerce.{table}")).scalar_one()
            if actual != expected:
                raise RuntimeError(f"Row-count mismatch for {table}: expected {expected}, got {actual}")
    return counts


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Load the generated CSV bundle into PostgreSQL.")
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--chunk-size", type=int, default=50_000)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is missing. Copy .env.example to .env or pass --database-url.")
    counts = load_bundle(args.data_dir, args.database_url, args.chunk_size)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()

