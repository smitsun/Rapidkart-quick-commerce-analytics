from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, PercentFormatter
except ModuleNotFoundError:  # Core CSV analysis remains usable in minimal environments.
    plt = None

from src.config import OUTPUT_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR


def _read_bool_csv(path: Path, dtype: dict | None = None) -> pd.DataFrame:
    return pd.read_csv(
        path,
        true_values=["True", "true"],
        false_values=["False", "false"],
        dtype=dtype,
    )


def _two_proportion_test(success_a: int, total_a: int, success_b: int, total_b: int) -> tuple[float, float]:
    rate_a = success_a / total_a
    rate_b = success_b / total_b
    pooled = (success_a + success_b) / (total_a + total_b)
    standard_error = np.sqrt(pooled * (1 - pooled) * (1 / total_a + 1 / total_b))
    z_score = (rate_b - rate_a) / standard_error
    p_value = math.erfc(abs(z_score) / math.sqrt(2))
    return float(z_score), float(p_value)


def _create_forecast(daily_orders: pd.Series, horizon: int = 28) -> pd.DataFrame:
    daily_orders = daily_orders.asfreq("D", fill_value=0).astype(float)
    day_number = np.arange(len(daily_orders))
    weekdays = pd.get_dummies(daily_orders.index.dayofweek, prefix="weekday", drop_first=True).astype(float)
    design = np.column_stack(
        [
            np.ones(len(daily_orders)),
            day_number,
            np.sin(2 * np.pi * day_number / 7),
            np.cos(2 * np.pi * day_number / 7),
            weekdays.to_numpy(),
        ]
    )
    coefficients, *_ = np.linalg.lstsq(design, daily_orders.to_numpy(), rcond=None)
    fitted = design @ coefficients
    residual_std = float(np.std(daily_orders.to_numpy() - fitted, ddof=design.shape[1]))

    future_index = pd.date_range(daily_orders.index.max() + pd.Timedelta(days=1), periods=horizon, freq="D")
    future_day = np.arange(len(daily_orders), len(daily_orders) + horizon)
    future_weekdays = pd.get_dummies(
        pd.Categorical(future_index.dayofweek, categories=range(7)),
        prefix="weekday",
        drop_first=True,
    ).astype(float)
    future_design = np.column_stack(
        [
            np.ones(horizon),
            future_day,
            np.sin(2 * np.pi * future_day / 7),
            np.cos(2 * np.pi * future_day / 7),
            future_weekdays.to_numpy(),
        ]
    )
    forecast = np.maximum(0, future_design @ coefficients)
    return pd.DataFrame(
        {
            "forecast_date": future_index,
            "forecast_orders": np.round(forecast, 1),
            "lower_95": np.round(np.maximum(0, forecast - 1.96 * residual_std), 1),
            "upper_95": np.round(forecast + 1.96 * residual_std, 1),
        }
    )


def _inventory_summary(data_dir: Path, products: pd.DataFrame, stores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    product_parts: list[pd.DataFrame] = []
    store_parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(data_dir / "fact_inventory_daily.csv", chunksize=100_000):
        if chunk.empty:
            continue
        product_parts.append(
            chunk.groupby("product_id", as_index=False)[["units_sold", "waste_units", "stockout_minutes"]].sum()
        )
        store_parts.append(
            chunk.groupby("store_id", as_index=False)[["units_sold", "waste_units", "stockout_minutes"]].sum()
        )
    if not product_parts:
        return pd.DataFrame(), pd.DataFrame()
    product_summary = pd.concat(product_parts).groupby("product_id", as_index=False).sum()
    product_summary = product_summary.merge(products[["product_id", "category", "subcategory"]], on="product_id")
    product_summary["waste_rate"] = product_summary["waste_units"] / (
        product_summary["units_sold"] + product_summary["waste_units"]
    ).replace(0, np.nan)
    store_summary = pd.concat(store_parts).groupby("store_id", as_index=False).sum()
    store_summary = store_summary.merge(stores[["store_id", "city", "zone"]], on="store_id")
    return product_summary, store_summary


def run_analysis(data_dir: Path, processed_dir: Path, output_dir: Path) -> dict:
    data_dir, processed_dir, output_dir = Path(data_dir), Path(processed_dir), Path(output_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    if plt is not None:
        plt.style.use("seaborn-v0_8-whitegrid")

    customers = _read_bool_csv(
        data_dir / "dim_customers.csv",
        dtype={"customer_id": "string"},
    )
    stores = pd.read_csv(data_dir / "dim_stores.csv")
    products = pd.read_csv(data_dir / "dim_products.csv")
    orders = _read_bool_csv(
        data_dir / "fact_orders.csv",
        dtype={"order_id": "string", "customer_id": "string", "store_id": "string"},
    )
    items = pd.read_csv(data_dir / "fact_order_items.csv")
    sessions = _read_bool_csv(
        data_dir / "fact_sessions.csv",
        dtype={"session_id": "string", "customer_id": "string", "order_id": "string"},
    )
    marketing = pd.read_csv(data_dir / "fact_marketing_spend.csv")

    orders["order_ts"] = pd.to_datetime(orders["order_ts"])
    customers["signup_date"] = pd.to_datetime(customers["signup_date"])
    marketing["spend_date"] = pd.to_datetime(marketing["spend_date"])

    item_costs = items.assign(
        item_revenue=items["quantity"] * items["unit_selling_price"],
        cogs=items["quantity"] * items["unit_cost"],
    ).groupby("order_id", as_index=False).agg(
        units=("quantity", "sum"), item_revenue=("item_revenue", "sum"), cogs=("cogs", "sum")
    )
    economics = orders.merge(item_costs, on="order_id", validate="one_to_one")
    economics["net_revenue"] = (
        economics["gross_merchandise_value"] - economics["discount_amount"]
        + economics["delivery_fee"] + economics["packaging_fee"] - economics["refund_amount"]
    )
    economics.loc[economics["status"] == "Cancelled", "net_revenue"] = 0.0
    economics["realized_cogs"] = np.where(economics["status"] == "Cancelled", 0.0, economics["cogs"])
    economics["contribution_margin"] = (
        economics["net_revenue"] - economics["realized_cogs"] - economics["estimated_delivery_cost"]
    )
    economics["is_on_time"] = economics["delivery_minutes"] <= economics["promised_minutes"]
    economics["order_date"] = economics["order_ts"].dt.date

    store_kpis = economics.groupby("store_id", as_index=False).agg(
        orders=("order_id", "count"),
        customers=("customer_id", "nunique"),
        gmv=("gross_merchandise_value", "sum"),
        net_revenue=("net_revenue", "sum"),
        contribution_margin=("contribution_margin", "sum"),
        avg_delivery_minutes=("delivery_minutes", "mean"),
        on_time_rate=("is_on_time", "mean"),
        cancellation_rate=("status", lambda x: (x == "Cancelled").mean()),
    ).merge(stores[["store_id", "city", "zone"]], on="store_id")
    store_kpis["margin_rate"] = store_kpis["contribution_margin"] / store_kpis["net_revenue"]

    valid_orders = economics[economics["status"] != "Cancelled"].copy()
    customer_kpis = valid_orders.groupby("customer_id", as_index=False).agg(
        first_order=("order_ts", "min"),
        last_order=("order_ts", "max"),
        frequency=("order_id", "count"),
        monetary=("net_revenue", "sum"),
        contribution_margin=("contribution_margin", "sum"),
    )
    analysis_date = orders["order_ts"].max() + pd.Timedelta(days=1)
    customer_kpis["recency_days"] = (analysis_date - customer_kpis["last_order"]).dt.days
    customer_kpis["r_score"] = pd.qcut(
        customer_kpis["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]
    ).astype(int)
    customer_kpis["f_score"] = pd.qcut(
        customer_kpis["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]
    ).astype(int)
    customer_kpis["m_score"] = pd.qcut(
        customer_kpis["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]
    ).astype(int)
    customer_kpis["rfm_score"] = customer_kpis[["r_score", "f_score", "m_score"]].sum(axis=1)
    customer_kpis["segment"] = pd.cut(
        customer_kpis["rfm_score"],
        bins=[0, 5, 8, 11, 15],
        labels=["At Risk", "Needs Attention", "Loyal", "Champions"],
    )

    sequence = orders.sort_values(["customer_id", "order_ts"]).copy()
    sequence["next_order_ts"] = sequence.groupby("customer_id")["order_ts"].shift(-1)
    sequence["repeat_within_30d"] = (
        (sequence["next_order_ts"] - sequence["order_ts"]).dt.total_seconds() / 86_400 <= 30
    )
    eligible = sequence[sequence["order_ts"] <= orders["order_ts"].max() - pd.Timedelta(days=30)].copy()
    eligible["service_group"] = np.select(
        [eligible["status"] == "Cancelled", eligible["status"] == "Refunded", eligible["delivery_minutes"] > 35],
        ["Cancelled", "Refunded", "Late (>35m)"],
        default="On time (<=35m)",
    )
    retention_by_service = eligible.groupby("service_group", as_index=False).agg(
        eligible_orders=("order_id", "count"),
        repeat_30d_rate=("repeat_within_30d", "mean"),
    )

    valid_orders["cohort_month"] = valid_orders.groupby("customer_id")["order_ts"].transform("min").dt.to_period("M").astype(str)
    valid_orders["order_month"] = valid_orders["order_ts"].dt.to_period("M")
    cohort_period = pd.PeriodIndex(valid_orders["cohort_month"], freq="M")
    valid_orders["cohort_index"] = (
        (valid_orders["order_month"].dt.year - cohort_period.year) * 12
        + valid_orders["order_month"].dt.month - cohort_period.month
    )
    cohort_counts = valid_orders.groupby(["cohort_month", "cohort_index"])["customer_id"].nunique().unstack(fill_value=0)
    cohort_retention = cohort_counts.div(cohort_counts.get(0, pd.Series(index=cohort_counts.index)), axis=0)

    experiment = sessions.groupby("experiment_variant").agg(
        sessions=("session_id", "count"), conversions=("converted", "sum"),
        view_rate=("viewed_product", "mean"), add_to_cart_rate=("added_to_cart", "mean"),
        checkout_rate=("checkout_started", "mean"), conversion_rate=("converted", "mean"),
    ).reset_index()
    control = experiment.set_index("experiment_variant").loc["Control"]
    treatment = experiment.set_index("experiment_variant").loc["Treatment"]
    z_score, p_value = _two_proportion_test(
        int(control["conversions"]), int(control["sessions"]),
        int(treatment["conversions"]), int(treatment["sessions"]),
    )
    experiment["absolute_lift_vs_control"] = experiment["conversion_rate"] - float(control["conversion_rate"])
    experiment["p_value"] = p_value
    experiment_economics = economics.groupby("experiment_variant", as_index=False).agg(
        conversion_contribution_margin=("contribution_margin", "sum"),
        avg_margin_per_conversion=("contribution_margin", "mean"),
        avg_discount_per_conversion=("discount_amount", "mean"),
    )
    experiment = experiment.merge(experiment_economics, on="experiment_variant", validate="one_to_one")
    experiment["contribution_margin_per_session"] = (
        experiment["conversion_contribution_margin"] / experiment["sessions"]
    )
    control = experiment.set_index("experiment_variant").loc["Control"]
    treatment = experiment.set_index("experiment_variant").loc["Treatment"]

    realized_items = items[items["order_id"].isin(valid_orders["order_id"])].copy()
    product_kpis = realized_items.assign(
        item_revenue=realized_items["quantity"] * realized_items["unit_selling_price"],
        gross_profit=realized_items["quantity"] * (realized_items["unit_selling_price"] - realized_items["unit_cost"]),
    ).groupby("product_id", as_index=False).agg(
        units=("quantity", "sum"), item_revenue=("item_revenue", "sum"), gross_profit=("gross_profit", "sum")
    ).merge(products[["product_id", "category", "subcategory", "brand_tier"]], on="product_id")

    daily_store = economics.groupby(["order_date", "store_id"], as_index=False).agg(
        orders=("order_id", "count"), gmv=("gross_merchandise_value", "sum"),
        net_revenue=("net_revenue", "sum"), contribution_margin=("contribution_margin", "sum"),
        avg_delivery_minutes=("delivery_minutes", "mean"), on_time_rate=("is_on_time", "mean"),
    )
    daily_orders = economics.set_index("order_ts").resample("D")["order_id"].count()
    forecast = _create_forecast(daily_orders)

    acquired = customers[
        customers["signup_date"].between(pd.Timestamp(orders["order_ts"].min().date()), pd.Timestamp(orders["order_ts"].max().date()))
    ].groupby(["city", "acquisition_channel"], as_index=False).agg(acquired_customers=("customer_id", "nunique"))
    spend = marketing.groupby(["city", "acquisition_channel"], as_index=False)["spend"].sum()
    channel_cac = spend.merge(acquired, on=["city", "acquisition_channel"], how="left")
    channel_cac["cac"] = channel_cac["spend"] / channel_cac["acquired_customers"].replace(0, np.nan)

    inventory_product, inventory_store = _inventory_summary(data_dir, products, stores)

    outputs = {
        "order_economics.csv": economics,
        "store_kpis.csv": store_kpis,
        "customer_rfm.csv": customer_kpis,
        "retention_by_service.csv": retention_by_service,
        "cohort_retention.csv": cohort_retention.reset_index(),
        "experiment_summary.csv": experiment,
        "product_kpis.csv": product_kpis,
        "daily_store_kpis.csv": daily_store,
        "demand_forecast.csv": forecast,
        "channel_cac.csv": channel_cac,
    }
    if not inventory_product.empty:
        outputs["inventory_product_kpis.csv"] = inventory_product
        outputs["inventory_store_kpis.csv"] = inventory_store
    for filename, frame in outputs.items():
        frame.to_csv(processed_dir / filename, index=False)

    kpis = {
        "orders": int(len(orders)),
        "customers": int(orders["customer_id"].nunique()),
        "gmv": round(float(economics["gross_merchandise_value"].sum()), 2),
        "net_revenue": round(float(economics["net_revenue"].sum()), 2),
        "contribution_margin": round(float(economics["contribution_margin"].sum()), 2),
        "contribution_margin_rate": round(float(economics["contribution_margin"].sum() / economics["net_revenue"].sum()), 4),
        "cancellation_rate": round(float((orders["status"] == "Cancelled").mean()), 4),
        "on_time_rate": round(float(economics.loc[economics["status"] != "Cancelled", "is_on_time"].mean()), 4),
        "control_conversion_rate": round(float(control["conversion_rate"]), 4),
        "treatment_conversion_rate": round(float(treatment["conversion_rate"]), 4),
        "experiment_absolute_lift": round(float(treatment["conversion_rate"] - control["conversion_rate"]), 4),
        "experiment_z_score": round(z_score, 3),
        "experiment_p_value": p_value,
        "control_margin_per_session": round(float(control["contribution_margin_per_session"]), 2),
        "treatment_margin_per_session": round(float(treatment["contribution_margin_per_session"]), 2),
    }
    (output_dir / "executive_kpis.json").write_text(json.dumps(kpis, indent=2), encoding="utf-8")

    if plt is not None:
        plt.style.use("seaborn-v0_8-whitegrid")

        service_order = ["On time (<=35m)", "Late (>35m)", "Refunded", "Cancelled"]
        retention_chart = retention_by_service.set_index("service_group").reindex(service_order).reset_index()
        fig, ax = plt.subplots(figsize=(9, 5))
        bars = ax.bar(
            retention_chart["service_group"],
            retention_chart["repeat_30d_rate"],
            color=["#2563EB", "#F59E0B", "#8B5CF6", "#DC2626"],
        )
        ax.bar_label(bars, labels=[f"{value:.1%}" for value in retention_chart["repeat_30d_rate"]], padding=4)
        ax.set(title="30-day repeat rate by service outcome", xlabel="", ylabel="Repeat rate", ylim=(0, 0.6))
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.tick_params(axis="x", rotation=8)
        fig.tight_layout()
        fig.savefig(output_dir / "retention_by_service.png", dpi=160)
        plt.close(fig)

        weakest = store_kpis.sort_values("contribution_margin").head(10).sort_values("contribution_margin")
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.barh(weakest["zone"], weakest["contribution_margin"], color="#DC2626")
        ax.set(title="Lowest-contribution stores", xlabel="Contribution margin (INR)", ylabel="")
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1_000_000:.1f}M"))
        fig.tight_layout()
        fig.savefig(output_dir / "store_margin_risk.png", dpi=160)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(daily_orders.index, daily_orders.values, label="Actual", color="#4C78A8", linewidth=1.2)
        ax.plot(forecast["forecast_date"], forecast["forecast_orders"], label="Forecast", color="#F58518")
        ax.fill_between(forecast["forecast_date"], forecast["lower_95"], forecast["upper_95"], alpha=0.2, color="#F58518")
        ax.set(title="Daily order demand with 28-day forecast", xlabel="", ylabel="Orders")
        ax.legend()
        fig.tight_layout()
        fig.savefig(output_dir / "demand_forecast.png", dpi=160)
        plt.close(fig)

    on_time_rate = float(retention_by_service.loc[retention_by_service["service_group"] == "On time (<=35m)", "repeat_30d_rate"].iloc[0])
    late_rate = float(retention_by_service.loc[retention_by_service["service_group"] == "Late (>35m)", "repeat_30d_rate"].iloc[0])
    weakest_store = store_kpis.sort_values("contribution_margin").iloc[0]
    margin_per_session_lift = float(
        treatment["contribution_margin_per_session"] - control["contribution_margin_per_session"]
    )
    experiment_decision = "launch the treatment with monitoring" if p_value < 0.05 and margin_per_session_lift > 0 else "do not launch the treatment yet"
    summary = f"""# Executive Summary

## Decision context

Management asked where profitability and retention are leaking and whether the checkout treatment should be launched.

## Findings

- The dataset contains {len(orders):,} orders from {orders['customer_id'].nunique():,} purchasing customers.
- Total contribution margin is INR {kpis['contribution_margin']:,.0f}, a {kpis['contribution_margin_rate']:.1%} margin rate.
- Orders delivered within 35 minutes have a {on_time_rate:.1%} 30-day repeat rate versus {late_rate:.1%} for late orders, a {(on_time_rate-late_rate):.1%} absolute gap.
- Treatment conversion is {float(treatment['conversion_rate']):.1%} versus {float(control['conversion_rate']):.1%} for control (two-sided p-value {p_value:.3g}).
- Treatment contribution margin per assigned session is INR {float(treatment['contribution_margin_per_session']):,.2f} versus INR {float(control['contribution_margin_per_session']):,.2f} for control.
- {weakest_store['zone']}, {weakest_store['city']} has the lowest simulated contribution margin at INR {weakest_store['contribution_margin']:,.0f}.

## Recommendations

1. Prioritise late-delivery reduction in the weakest service zones and monitor the 30-day repeat rate as the outcome metric.
2. Based on both statistical significance and contribution per assigned session, **{experiment_decision}**; retain a margin guardrail after rollout.
3. Review products with high stockout minutes and positive gross profit separately from products with high waste and weak margins.

## Important limitation

This is synthetic portfolio data. The analysis demonstrates a reproducible method and must not be presented as evidence about a real company.
"""
    (output_dir / "executive_summary.md").write_text(summary, encoding="utf-8")
    return kpis


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quick-commerce analytical workflow.")
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.data_dir, args.processed_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
