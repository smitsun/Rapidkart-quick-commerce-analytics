from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import OUTPUT_DIR, RAW_DATA_DIR


REQUIRED_COLUMNS = {
    "dim_customers.csv": {"customer_id", "signup_date", "city", "acquisition_channel", "is_prime"},
    "dim_stores.csv": {"store_id", "city", "zone", "capacity_orders_per_hour"},
    "dim_products.csv": {"product_id", "category", "unit_cost", "list_price", "shelf_life_days"},
    "fact_orders.csv": {
        "order_id", "customer_id", "store_id", "order_ts", "status",
        "gross_merchandise_value", "discount_amount", "refund_amount",
    },
    "fact_order_items.csv": {
        "order_item_id", "order_id", "product_id", "quantity",
        "unit_selling_price", "unit_cost",
    },
    "fact_sessions.csv": {
        "session_id", "customer_id", "experiment_variant", "viewed_product",
        "added_to_cart", "checkout_started", "converted", "order_id",
    },
    "fact_inventory_daily.csv": {
        "inventory_date", "store_id", "product_id", "opening_stock",
        "units_received", "units_sold", "waste_units", "closing_stock",
    },
    "fact_marketing_spend.csv": {
        "spend_date", "city", "acquisition_channel", "impressions", "clicks", "spend",
    },
}


def _record(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def validate_csv_bundle(data_dir: Path, report_path: Path | None = None) -> dict:
    data_dir = Path(data_dir)
    checks: list[dict] = []

    for filename, required in REQUIRED_COLUMNS.items():
        path = data_dir / filename
        _record(checks, f"{filename}: exists", path.exists(), str(path))
        if path.exists():
            columns = set(pd.read_csv(path, nrows=0).columns)
            missing = sorted(required - columns)
            _record(checks, f"{filename}: required columns", not missing, f"missing={missing}")

    if not all(check["passed"] for check in checks):
        report = {"passed": False, "checks": checks}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    customers = pd.read_csv(data_dir / "dim_customers.csv")
    stores = pd.read_csv(data_dir / "dim_stores.csv")
    products = pd.read_csv(data_dir / "dim_products.csv")
    orders = pd.read_csv(data_dir / "fact_orders.csv")
    items = pd.read_csv(data_dir / "fact_order_items.csv")
    sessions = pd.read_csv(
        data_dir / "fact_sessions.csv",
        dtype={"session_id": "string", "customer_id": "string", "order_id": "string"},
    )

    _record(checks, "customer primary key", customers["customer_id"].is_unique, f"rows={len(customers):,}")
    _record(checks, "store primary key", stores["store_id"].is_unique, f"rows={len(stores):,}")
    _record(checks, "product primary key", products["product_id"].is_unique, f"rows={len(products):,}")
    _record(checks, "order primary key", orders["order_id"].is_unique, f"rows={len(orders):,}")
    _record(checks, "order-item primary key", items["order_item_id"].is_unique, f"rows={len(items):,}")
    _record(checks, "session primary key", sessions["session_id"].is_unique, f"rows={len(sessions):,}")

    _record(
        checks,
        "order customer foreign key",
        orders["customer_id"].isin(customers["customer_id"]).all(),
        "every order customer exists",
    )
    _record(
        checks,
        "order store foreign key",
        orders["store_id"].isin(stores["store_id"]).all(),
        "every order store exists",
    )
    _record(
        checks,
        "item order foreign key",
        items["order_id"].isin(orders["order_id"]).all(),
        "every item order exists",
    )
    _record(
        checks,
        "item product foreign key",
        items["product_id"].isin(products["product_id"]).all(),
        "every item product exists",
    )
    _record(
        checks,
        "session customer foreign key",
        sessions["customer_id"].isin(customers["customer_id"]).all(),
        "every session customer exists",
    )

    item_value = (items["quantity"] * items["unit_selling_price"]).groupby(items["order_id"]).sum()
    reconciled = orders.set_index("order_id")["gross_merchandise_value"].sub(item_value).abs()
    _record(
        checks,
        "GMV reconciles to items",
        bool((reconciled.fillna(np.inf) <= 0.05).all()),
        f"max_absolute_difference={reconciled.max():.4f}",
    )
    _record(
        checks,
        "valid order status",
        orders["status"].isin(["Delivered", "Cancelled", "Refunded"]).all(),
        str(orders["status"].value_counts().to_dict()),
    )
    order_dates = pd.to_datetime(orders["order_ts"])
    _record(
        checks,
        "orders span all calendar months",
        order_dates.dt.to_period("M").nunique() == 12,
        f"min={order_dates.min()}; max={order_dates.max()}; months={order_dates.dt.to_period('M').nunique()}",
    )
    _record(
        checks,
        "non-negative financials",
        (orders[["gross_merchandise_value", "discount_amount", "refund_amount"]] >= 0).all().all(),
        "GMV, discount, and refund are non-negative",
    )

    bool_columns = ["viewed_product", "added_to_cart", "checkout_started", "converted"]
    for column in bool_columns:
        if sessions[column].dtype == object:
            sessions[column] = sessions[column].astype(str).str.lower().map({"true": True, "false": False})
    logical_funnel = (
        (~sessions["added_to_cart"] | sessions["viewed_product"])
        & (~sessions["checkout_started"] | sessions["added_to_cart"])
        & (~sessions["converted"] | sessions["checkout_started"])
    )
    _record(checks, "logical session funnel", logical_funnel.all(), "later stages require earlier stages")
    converted_sessions = sessions[sessions["converted"]]
    _record(
        checks,
        "converted sessions link to orders",
        converted_sessions["order_id"].notna().all()
        and converted_sessions["order_id"].isin(orders["order_id"]).all(),
        f"converted_sessions={len(converted_sessions):,}",
    )
    variant_summary = sessions.groupby("experiment_variant")["converted"].agg(["count", "mean"])
    assignment_imbalance = float((variant_summary["count"].max() - variant_summary["count"].min()) / len(sessions))
    observed_lift = float(variant_summary.loc["Treatment", "mean"] - variant_summary.loc["Control", "mean"])
    _record(
        checks,
        "balanced experiment assignment",
        assignment_imbalance <= 0.02,
        f"group_counts={variant_summary['count'].to_dict()}",
    )
    _record(
        checks,
        "embedded experiment lift",
        0.035 <= observed_lift <= 0.045,
        f"absolute_lift={observed_lift:.4f}",
    )

    inventory_path = data_dir / "fact_inventory_daily.csv"
    inventory_rows = 0
    inventory_equation_errors = 0
    inventory_negative_rows = 0
    for chunk in pd.read_csv(inventory_path, chunksize=100_000):
        inventory_rows += len(chunk)
        calculated_close = (
            chunk["opening_stock"] + chunk["units_received"]
            - chunk["units_sold"] - chunk["waste_units"]
        )
        inventory_equation_errors += int((calculated_close != chunk["closing_stock"]).sum())
        inventory_negative_rows += int(
            (chunk[["opening_stock", "units_received", "units_sold", "waste_units", "closing_stock"]] < 0)
            .any(axis=1)
            .sum()
        )
    _record(
        checks,
        "inventory balance equation",
        inventory_equation_errors == 0,
        f"rows={inventory_rows:,}; errors={inventory_equation_errors:,}",
    )
    _record(
        checks,
        "non-negative inventory",
        inventory_negative_rows == 0,
        f"invalid_rows={inventory_negative_rows:,}",
    )

    metadata_path = data_dir / "generation_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_orders = metadata["row_counts"]["fact_orders"]
        _record(checks, "metadata order count", len(orders) == expected_orders, f"expected={expected_orders:,}")

    report = {
        "passed": all(check["passed"] for check in checks),
        "summary": {
            "checks": len(checks),
            "passed": sum(check["passed"] for check in checks),
            "failed": sum(not check["passed"] for check in checks),
        },
        "checks": checks,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated quick-commerce CSV files.")
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--report", type=Path, default=OUTPUT_DIR / "data_quality_report.json")
    args = parser.parse_args()
    report = validate_csv_bundle(args.data_dir, args.report)
    print(json.dumps(report["summary"], indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
