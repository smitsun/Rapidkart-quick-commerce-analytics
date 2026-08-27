from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SQL_DIR = PROJECT_ROOT / "sql"


@dataclass(frozen=True)
class GeneratorConfig:
    n_orders: int = 250_000
    seed: int = 42
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"
    inventory_days: int = 365
    output_dir: Path = RAW_DATA_DIR

    @property
    def n_customers(self) -> int:
        # The simulation averages roughly five to seven orders per customer.
        return min(self.n_orders, max(500, int(self.n_orders / 5.5)))


