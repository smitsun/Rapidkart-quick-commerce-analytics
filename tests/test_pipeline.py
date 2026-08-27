from __future__ import annotations

import json

import pandas as pd

from src.analyze import run_analysis
from src.config import GeneratorConfig
from src.data_quality import validate_csv_bundle
from src.generate_data import generate_project_data


def test_small_end_to_end_pipeline(tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    metadata = generate_project_data(
        GeneratorConfig(n_orders=3_000, seed=42, inventory_days=3, output_dir=raw)
    )

    assert metadata["row_counts"]["fact_orders"] == 3_000
    assert metadata["row_counts"]["fact_order_items"] > 3_000
    assert metadata["row_counts"]["fact_sessions"] > 3_000

    orders = pd.read_csv(raw / "fact_orders.csv", parse_dates=["order_ts"])
    assert orders["order_ts"].dt.to_period("M").nunique() == 12

    report = validate_csv_bundle(raw, outputs / "quality.json")
    assert report["passed"], json.dumps(report, indent=2)

    kpis = run_analysis(raw, processed, outputs)
    assert kpis["orders"] == 3_000
    assert 0.035 <= kpis["experiment_absolute_lift"] <= 0.045
    assert (processed / "store_kpis.csv").exists()
    assert (outputs / "executive_summary.md").exists()

    retention = pd.read_csv(processed / "retention_by_service.csv").set_index("service_group")
    assert retention.loc["On time (<=35m)", "repeat_30d_rate"] > retention.loc["Late (>35m)", "repeat_30d_rate"]


def test_inventory_balance_is_exact(tmp_path):
    raw = tmp_path / "raw"
    generate_project_data(
        GeneratorConfig(n_orders=800, seed=7, inventory_days=2, output_dir=raw)
    )
    inventory = pd.read_csv(raw / "fact_inventory_daily.csv")
    calculated = (
        inventory["opening_stock"] + inventory["units_received"]
        - inventory["units_sold"] - inventory["waste_units"]
    )
    assert calculated.equals(inventory["closing_stock"])
