from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
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
        "control_margin_per_session": round(float(control["cu×­¶¶‰žËkºwµç@¢$öffÆ–æR#¢SRãÀ¢Ð¢&÷w3¢Æ—7E¶F–7EÒÒµÐ¢f÷"FFR–âBæFFU÷&ævR†6öæf–rç7F'EöFFRÂ6öæf–ræVæEöFFRÂg&WÒ$B"“ ¢6V6öæÆ—G’Òã#"–bFFRæÖöçF‚–âƒÂÂ"’VÇ6Rã ¢f÷"6—G’–â4•D”U3 ¢f÷"6†ææVÂ–â4„ääTÅ3 ¢–×&W76–öç2Ò–çB‡&æræ–çFVvW'2ƒ%óÂ…ó’¢6V6öæÆ—G’¢7G"ÒfÆöB‡&ærçVæ–f÷&Òƒã"ÂãSR’’–b6†ææVÂÒ$÷&væ–2"VÇ6RfÆöB‡&ærçVæ–f÷&ÒƒãBÂã’’¢6Æ–6·2Ò–çB†–×&W76–öç2¢7G"¢7VæBÒ6Æ–6·2¢6†ææVÅö75¶6†ææVÅÒ¢fÆöB‡&ærçVæ–f÷&Òƒãƒ‚ÂãR’¢&÷w2æVæB€¢°¢'7VæEöFFR#¢FFRæFFR‚’À¢&6—G’#¢6—G’À¢&7V—6—F–öåö6†ææVÂ#¢6†ææVÂÀ¢&6×–våö–B#¢b'¶6†ææVÅ³£5ÒçWW"‚—Ò×¶FFS¢U’V×Ò"À¢&–×&W76–öç2#¢–×&W76–öç2À¢&6Æ–6·2#¢6Æ–6·2À¢'7VæB#¢&÷VæB‡7VæBÂ"’À¢Ð¢¢&WGW&âBäFFg&ÖR‡&÷w2  ¦FVb÷w&—FUö–çfVçF÷'•ö77b€¢6öæf–s¢vVæW&F÷$6öæf–rÀ¢&æs¢çç&æFöÒävVæW&F÷"À¢7F÷&W3¢BäFFg&ÖRÀ¢&öGV7G3¢BäFFg&ÖRÀ¢6öÆEöÖ¢F–7E·GWÆRÂ–çEÒÀ¢’Óâ–çC ¢÷WGWE÷F‚Ò6öæf–ræ÷WGWEöF—"ò&f7Eö–çfVçF÷'•öF–Ç’æ77b ¢–b6öæf–ræ–çfVçF÷'•öF—2ÃÒ ¢BäFFg&ÖR€¢6öÇVÖç3Õ°¢&–çfVçF÷'•öFFR"Â'7F÷&Uö–B"Â'&öGV7Eö–B"Â&÷Væ–æu÷7Fö6²"À¢'Væ—G5÷&V6V—fVB"Â'Væ—G5÷6öÆB"Â'v7FU÷Væ—G2"Â&6Æ÷6–æu÷7Fö6²"À¢'7Fö6¶÷WEöÖ–çWFW2"À¢Ð¢’çFõö77b†÷WGWE÷F‚Â–æFWƒÔfÇ6R¢&WGW&â  ¢VæBÒBåF–ÖW7F×†6öæf–ræVæEöFFR¢–çfVçF÷'•÷7F'BÒÖ‚‡BåF–ÖW7F×†6öæf–rç7F'EöFFR’ÂVæBÒBåF–ÖVFVÇF†F—3Ö6öæf–ræ–çfVçF÷'•öF—2Ò’¢w&÷FUö†VFW"ÒfÇ6P¢F÷FÅ÷&÷w2Ò ¢W&—6†&ÆRÒ&öGV7G5²'6†VÆeöÆ–fUöF—2%ÒçFõöçV×’‚’ÃÒ@¢&öGV7Eö–G2Ò&öGV7G5²'&öGV7Eö–B%ÒçFõöçV×’‚ ¢f÷"FFR–âBæFFU÷&ævR†–çfVçF÷'•÷7F'BÂVæBÂg&WÒ$B"“ ¢6‡Væ³¢Æ—7E¶F–7EÒÒµÐ¢vVV¶VæBÒFFRæF–ögvVV²ãÒP¢f÷"7F÷&Uö–B–â7F÷&W5²'7F÷&Uö–B%Ó ¢f÷"&öGV7Eö–æFW‚Â&öGV7Eö–B–âVçVÖW&FR‡&öGV7Eö–G2“ ¢6öÆBÒ–çB‡6öÆEöÖævWB‚†FFRæFFR‚’Â7F÷&Uö–BÂ&öGV7Eö–B’Â’¢÷Væ–ærÒ–çB‡&æræ–çFVvW'2ƒBÂ#B’²Ö–âƒ‚Â6öÆBòò"’¢v7FU÷&FRÒãSR–bW&—6†&ÆU·&öGV7Eö–æFW…ÒVÇ6Rã`¢v7FRÒ–çB‡&æræ&–æöÖ–Â†÷Væ–ærÂv7FU÷&FR’¢F&vWEö6Æ÷6RÒ–çB‡&æræ–çFVvW'2ƒ2Â‚’¢&V6V—fVBÒÖ‚ƒÂ6öÆB²v7FR²F&vWEö6Æ÷6RÒ÷Væ–ær¢6Æ÷6–ærÒ÷Væ–ær²&V6V—fVBÒ6öÆBÒv7FP¢&W77W&RÒ6öÆBòÖ‚ƒÂ÷Væ–ær¢7Fö6¶÷WE÷&ö&&–Æ—G’ÒÖ–âƒãƒ"Âã#R²ã#¢Ö‚ƒÂ&W77W&RÒãr’²ƒã‚–bvVV¶VæBVÇ6R’¢7Fö6¶÷WEöÖ–çWFW2Ò–çB‡&æræ–çFVvW'2ƒ#Â3’’–b&ærç&æFöÒ‚’Â7Fö6¶÷WE÷&ö&&–Æ—G’VÇ6R ¢6‡Væ²æVæB€¢°¢&–çfVçF÷'•öFFR#¢FFRæFFR‚’À¢'7F÷&Uö–B#¢7F÷&Uö–BÀ¢'&öGV7Eö–B#¢&öGV7Eö–BÀ¢&÷Væ–æu÷7Fö6²#¢÷Væ–ærÀ¢'Væ—G5÷&V6V—fVB#¢&V6V—fVBÀ¢'Væ—G5÷6öÆB#¢6öÆBÀ¢'v7FU÷Væ—G2#¢v7FRÀ¢&6Æ÷6–æu÷7Fö6²#¢6Æ÷6–ærÀ¢'7Fö6¶÷WEöÖ–çWFW2#¢7Fö6¶÷WEöÖ–çWFW2À¢Ð¢¢BäFFg&ÖR†6‡Væ²’çFõö77b€¢÷WGWE÷F‚À¢ÖöFSÒ&"–bw&÷FUö†VFW"VÇ6R'r"À¢†VFW#Öæ÷Bw&÷FUö†VFW"À¢–æFWƒÔfÇ6RÀ¢¢w&÷FUö†VFW"ÒG'VP¢F÷FÅ÷&÷w2³ÒÆVâ†6‡Væ²¢&WGW&âF÷FÅ÷&÷w0  ¦FVbvVæW&FU÷&ö¦V7EöFF†6öæf–s¢vVæW&F÷$6öæf–r’ÓâF–7C ¢6öæf–ræ÷WGWEöF—"æÖ¶F—"‡&VçG3ÕG'VRÂW†—7Eöö³ÕG'VR¢&ærÒçç&æFöÒæFVfVÇE÷&ær†6öæf–rç6VVB¢7F÷&W2ÒöÖ¶U÷7F÷&W2‡&ær¢&öGV7G2ÒöÖ¶U÷&öGV7G2‡&ær¢7W7FöÖW'2Â7W7FöÖW%ö†–FFVâÒöÖ¶Uö7W7FöÖW'2†6öæf–rÂ&ær ¢7F÷&W2çFõö77b†6öæf–ræ÷WGWEöF—"ò&F–Õ÷7F÷&W2æ77b"Â–æFWƒÔfÇ6R¢&öGV7G2çFõö77b†6öæf–ræ÷WGWEöF—"ò&F–Õ÷&öGV7G2æ77b"Â–æFWƒÔfÇ6R¢7W7FöÖW'2çFõö77b†6öæf–ræ÷WGWEöF—"ò&F–Õö7W7FöÖW'2æ77b"Â–æFWƒÔfÇ6R ¢÷&FW'2Â—FV×2Â6öÆEöÖÒöÖ¶Uö÷&FW'5öæEö—FV×2€¢6öæf–rÂ&ærÂ7W7FöÖW'2Â7W7FöÖW%ö†–FFVâÂ7F÷&W2Â&öGV7G0¢¢÷&FW'2çFõö77b†6öæf–ræ÷WGWEöF—"ò&f7Eö÷&FW'2æ77b"Â–æFWƒÔfÇ6R¢—FV×2çFõö77b†6öæf–ræ÷WGWEöF—"ò&f7Eö÷&FW%ö—FV×2æ77b"Â–æFWƒÔfÇ6R¢—FVÕö6÷VçBÒÆVâ†—FV×2¢FVÂ—FV×0 ¢2ÖFW&–Æ—6R–çfVçF÷'’&Vf÷&R6W76–öç26òF†RÆ&vR6öÆB×Væ—BÆöö·W6â&R&VÆV6VBà¢–çfVçF÷'•ö6÷VçBÒ÷w&—FUö–çfVçF÷'•ö77b†6öæf–rÂ&ærÂ7F÷&W2Â&öGV7G2Â6öÆEöÖ¢FVÂ6öÆEöÖ  ¢6W76–öç2ÒöÖ¶U÷6W76–öç2‡&ærÂ÷&FW'2Â7W7FöÖW'2Â6öæf–rç7F'EöFFRÂ6öæf–ræVæEöFFR¢6W76–öç2çFõö77b†6öæf–ræ÷WGWEöF—"ò&f7E÷6W76–öç2æ77b"Â–æFWƒÔfÇ6R¢6W76–öåö6÷VçBÒÆVâ‡6W76–öç2¢FVÂ6W76–öç0 ¢Ö&¶WF–ærÒöÖ¶UöÖ&¶WF–æu÷7VæB†6öæf–rÂ&ær¢Ö&¶WF–ærçFõö77b†6öæf–ræ÷WGWEöF—"ò&f7EöÖ&¶WF–æu÷7VæBæ77b"Â–æFWƒÔfÇ6R¢Ö&¶WF–æuö6÷VçBÒÆVâ†Ö&¶WF–ær¢FVÂÖ&¶WF–æp ¢ÖWFFFÒ°¢'&ö¦V7B#¢%V–6²Ô6öÖÖW&6R&öf—F&–Æ—G’b&WFVçF–öâæÇ—F–72"À¢'7–çF†WF–5öFF#¢G'VRÀ¢'6VVB#¢6öæf–rç6VVBÀ¢&FFU÷&ævR#¢¶6öæf–rç7F'EöFFRÂ6öæf–ræVæEöFFUÒÀ¢'&÷uö6÷VçG2#¢°¢&F–Õö7W7FöÖW'2#¢ÆVâ†7W7FöÖW'2’À¢&F–Õ÷7F÷&W2#¢ÆVâ‡7F÷&W2’À¢&F–Õ÷&öGV7G2#¢ÆVâ‡&öGV7G2’À¢&f7Eö÷&FW'2#¢ÆVâ†÷&FW'2’À¢&f7Eö÷&FW%ö—FV×2#¢—FVÕö6÷VçBÀ¢&f7E÷6W76–öç2#¢6W76–öåö6÷VçBÀ¢&f7Eö–çfVçF÷'•öF–Ç’#¢–çfVçF÷'•ö6÷VçBÀ¢&f7EöÖ&¶WF–æu÷7VæB#¢Ö&¶WF–æuö6÷VçBÀ¢ÒÀ¢&VÖ&VFFVE÷GFW&ç5÷Fõ÷fÆ–FFR#¢°¢%G&VFÖVçB6W76–öç2†fR&÷WBf÷W"W&6VçFvRö–çG2†–v†W"6öçfW'6–öââ"À¢$ÆFRÂ6æ6VÆÆVBÂæB&VgVæFVB÷&FW'2&VGV6R3ÖF’&WVB&V†f–÷W"â"À¢%&–âÂ'W6‚†÷W'2ÂF—7Fæ6RÂæB7F÷&RW&f÷&Öæ6RffV7BFVÆ—fW'’F–ÖRâ"À¢$F—66÷VçG26âÆ–gB6öçfW'6–öâv†–ÆRW&öF–ær6öçG&–'WF–öâÖ&v–ââ"À¢%W&—6†&ÆR&öGV7G2†fRw&VFW"–çfVçF÷'’v7FRâ"À¢ÒÀ¢Ð¢v—F‚†6öæf–ræ÷WGWEöF—"ò&vVæW&F–öåöÖWFFFæ§6öâ"’æ÷Vâ‚'r"ÂVæ6öF–æsÒ'WFbÓ‚"’2†æFÆS ¢§6öâæGV×†ÖWFFFÂ†æFÆRÂ–æFVçCÓ"¢&WGW&âÖWFFF  ¦FVb'6Uö&w2‚’Óâ&w'6RäæÖW76S ¢'6W"Ò&w'6Rä&wVÖVçE'6W"†FW67&—F–öãÒ$vVæW&FRF†R7–çF†WF–2V–6²Ö6öÖÖW&6RFF6WBâ"¢'6W"æFEö&wVÖVçB‚"ÒÖ÷&FW'2"ÂG—SÖ–çBÂFVfVÇCÓ#SóÂ†VÇÒ$W†7BçVÖ&W"öb÷&FW'2FòvVæW&FRâ"¢'6W"æFEö&wVÖVçB‚"Ò×6VVB"ÂG—SÖ–çBÂFVfVÇCÓC"¢'6W"æFEö&wVÖVçB‚"ÒÖ–çfVçF÷'’ÖF—2"ÂG—SÖ–çBÂFVfVÇCÓ3cRÂ†VÇÒ%W6RFò6¶—–çfVçF÷'’&÷w2â"¢'6W"æFEö&wVÖVçB‚"ÒÖ÷WGWBÖF—""ÂG—SÕF‚ÂFVfVÇCÔæöæR¢&WGW&â'6W"ç'6Uö&w2‚  ¦FVbÖ–â‚’ÓâæöæS ¢&w2Ò'6Uö&w2‚¢6öæf–rÒvVæW&F÷$6öæf–r€¢åö÷&FW'3Ö&w2æ÷&FW'2À¢6VVCÖ&w2ç6VVBÀ¢–çfVçF÷'•öF—3Ö&w2æ–çfVçF÷'•öF—2À¢÷WGWEöF—#Ö&w2æ÷WGWEöF—"÷"$uôDDôD•"À¢¢ÖWFFFÒvVæW&FU÷&ö¦V7EöFF†6öæf–r¢&–çB†§6öâæGV×2†ÖWFFFÂ–æFVçCÓ"’  ¦–bõöæÖUõòÓÒ%õöÖ–åõò# ¢Ö–â‚