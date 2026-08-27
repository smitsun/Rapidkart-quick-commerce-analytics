from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.analyze import run_analysis
from src.config import GeneratorConfig, OUTPUT_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.data_quality import validate_csv_bundle
from src.generate_data import generate_project_data


def _load_local_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    _load_local_env()
    parser = argparse.ArgumentParser(description="Run the complete quick-commerce portfolio pipeline.")
    parser.add_argument("--orders", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inventory-days", type=int, default=365)
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--load-postgres", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    print("1/4 Generating data")
    metadata = generate_project_data(
        GeneratorConfig(
            n_orders=args.orders,
            seed=args.seed,
            inventory_days=args.inventory_days,
            output_dir=args.data_dir,
        )
    )

    print("2/4 Validating data")
    quality_report = validate_csv_bundle(args.data_dir, args.output_dir / "data_quality_report.json")
    if not quality_report["passed"]:
        raise SystemExit("Data-quality checks failed. See outputs/data_quality_report.json.")

    if args.load_postgres:
        print("3/4 Loading PostgreSQL")
        if not args.database_url:
            raise SystemExit("--load-postgres requires DATABASE_URL in .env or --database-url.")
        from src.load_postgres import load_bundle

        database_counts = load_bundle(args.data_dir, args.database_url)
    else:
        print("3/4 PostgreSQL load skipped (pass --load-postgres to enable)")
        database_counts = None

    print("4/4 Running analysis")
    kpis = run_analysis(args.data_dir, args.processed_dir, args.output_dir)
    result = {
        "generated_rows": metadata["row_counts"],
        "quality_checks": quality_report["summary"],
        "database_rows": database_counts,
        "executive_kpis": kpis,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
