from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import GeneratorConfig, RAW_DATA_DIR


CITIES = {
    "Bengaluru": (0.26, ["Indiranagar", "Whitefield", "HSR Layout", "Yelahanka"]),
    "Mumbai": (0.20, ["Andheri", "Powai", "Bandra", "Thane"]),
    "Delhi NCR": (0.18, ["Gurugram", "Noida", "Dwarka", "Saket"]),
    "Hyderabad": (0.15, ["Gachibowli", "Madhapur", "Kondapur", "Secunderabad"]),
    "Pune": (0.12, ["Hinjewadi", "Kharadi", "Baner", "Viman Nagar"]),
    "Chennai": (0.09, ["Velachery", "OMR", "Anna Nagar", "Adyar"]),
}

CHANNELS = ["Organic", "Paid Search", "Social", "Referral", "Partnership", "Offline"]
CHANNEL_PROBS = [0.30, 0.21, 0.17, 0.15, 0.11, 0.06]

CATEGORY_MAP = {
    "Fruits & Vegetables": ["Fresh Fruits", "Fresh Vegetables", "Herbs"],
    "Dairy & Breakfast": ["Milk", "Curd", "Eggs", "Breakfast"],
    "Snacks": ["Chips", "Biscuits", "Namkeen"],
    "Beverages": ["Soft Drinks", "Juices", "Tea & Coffee"],
    "Staples": ["Rice", "Flour", "Pulses", "Cooking Oil"],
    "Personal Care": ["Skin Care", "Hair Care", "Oral Care"],
    "Home Care": ["Cleaning", "Laundry", "Paper Products"],
    "Frozen Food": ["Frozen Snacks", "Ice Cream", "Ready Meals"],
    "Baby Care": ["Diapers", "Baby Food", "Baby Hygiene"],
    "Pet Care": ["Pet Food", "Pet Treats", "Pet Hygiene"],
}


def _make_stores(rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict] = []
    store_number = 1
    for city, (_, zones) in CITIES.items():
        for zone in zones:
            rows.append(
                {
                    "store_id": f"S{store_number:03d}",
                    "city": city,
                    "zone": zone,
                    "opened_date": (
                        pd.Timestamp("2022-01-01")
                        + pd.Timedelta(days=int(rng.integers(0, 900)))
                    ).date(),
                    "capacity_orders_per_hour": int(rng.integers(45, 91)),
                    "delivery_speed_factor": round(float(rng.uniform(0.88, 1.18)), 3),
                }
            )
            store_number += 1
    return pd.DataFrame(rows)


def _make_products(rng: np.random.Generator, n_products: int = 120) -> pd.DataFrame:
    price_ranges = {
        "Fruits & Vegetables": (25, 180, 0.67, 5),
        "Dairy & Breakfast": (30, 250, 0.72, 12),
        "Snacks": (10, 220, 0.61, 150),
        "Beverages": (20, 400, 0.64, 120),
        "Staples": (35, 900, 0.78, 240),
        "Personal Care": (45, 800, 0.57, 365),
        "Home Care": (35, 700, 0.59, 365),
        "Frozen Food": (50, 450, 0.66, 90),
        "Baby Care": (80, 1_200, 0.73, 240),
        "Pet Care": (60, 1_000, 0.69, 240),
    }
    categories = list(CATEGORY_MAP)
    rows: list[dict] = []
    for i in range(n_products):
        category = categories[i % len(categories)]
        subcategory = CATEGORY_MAP[category][(i // len(categories)) % len(CATEGORY_MAP[category])]
        low, high, cost_ratio, shelf_life = price_ranges[category]
        list_price = round(float(np.exp(rng.uniform(np.log(low), np.log(high)))), 2)
        noisy_cost_ratio = float(np.clip(rng.normal(cost_ratio, 0.035), 0.48, 0.84))
        rows.append(
            {
                "product_id": f"P{i + 1:04d}",
                "category": category,
                "subcategory": subcategory,
                "brand_tier": rng.choice(["Value", "Mass", "Premium"], p=[0.28, 0.52, 0.20]),
                "unit_cost": round(list_price * noisy_cost_ratio, 2),
                "list_price": list_price,
                "shelf_life_days": int(max(2, round(rng.normal(shelf_life, shelf_life * 0.12)))),
            }
        )
    return pd.DataFrame(rows)


def _make_customers(config: GeneratorConfig, rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    city_names = list(CITIES)
    city_probs = [CITIES[name][0] for name in city_names]
    signup_start = pd.Timestamp(config.start_date) - pd.Timedelta(days=120)
    signup_span = (pd.Timestamp(config.end_date) - signup_start).days - 90

    cities = rng.choice(city_names, size=config.n_customers, p=city_probs)
    channels = rng.choice(CHANNELS, size=config.n_customers, p=CHANNEL_PROBS)
    signup_offsets = rng.integers(0, signup_span + 1, size=config.n_customers)
    signup_dates = signup_start + pd.to_timedelta(signup_offsets, unit="D")
    loyalty = rng.beta(2.1, 2.3, size=config.n_customers)
    is_prime = rng.random(config.n_customers) < (0.12 + 0.30 * loyalty)
    base_gap_days = np.clip(rng.gamma(2.2, 5.0, size=config.n_customers), 2.0, 32.0)
    base_gap_days = base_gap_days * np.where(is_prime, 0.72, 1.0)

    frame = pd.DataFrame(
        {
            "customer_id": [f"C{i + 1:07d}" for i in range(config.n_customers)],
            "signup_date": signup_dates.date,
            "city": cities,
            "acquisition_channel": channels,
            "age_band": rng.choice(
                ["18-24", "25-34", "35-44", "45-54", "55+"],
                size=config.n_customers,
                p=[0.18, 0.39, 0.25, 0.12, 0.06],
            ),
            "is_prime": is_prime,
        }
    )
    hidden = {
        "loyalty": loyalty,
        "base_gap_days": base_gap_days,
        "signup_timestamps": signup_dates,
    }
    return frame, hidden


def _order_time_for_day(day: pd.Timestamp, rng: np.random.Generator) -> pd.Timestamp:
    hour = int(rng.choice([7, 8, 9, 10, 11, 12, 13, 17, 18, 19, 20, 21, 22], p=[.03, .05, .06, .05, .05, .07, .06, .07, .11, .14, .14, .11, .06]))
    return day.normalize() + pd.Timedelta(
        hours=hour,
        minutes=int(rng.integers(0, 60)),
        seconds=int(rng.integers(0, 60)),
    )


def _make_orders_and_items(
    config: GeneratorConfig,
    rng: np.random.Generator,
    customers: pd.DataFrame,
    customer_hidden: dict,
    stores: pd.DataFrame,
    products: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple, int]]:
    start = pd.Timestamp(config.start_date)
    end = pd.Timestamp(config.end_date) + pd.Timedelta(hours=23, minutes=59)
    store_lookup = {
        city: stores.index[stores["city"] == city].to_numpy() for city in CITIES
    }
    product_popularity = np.linspace(1.8, 0.55, len(products))
    product_popularity = product_popularity / product_popularity.sum()
    order_count_by_customer = np.zeros(len(customers), dtype=np.int32)
    active_customers = np.ones(len(customers), dtype=bool)
    available_after = np.full(len(customers), start.to_datetime64(), dtype="datetime64[ns]")
    signup_timestamps = customer_hidden["signup_timestamps"].to_numpy(dtype="datetime64[ns]")
    prime_flags = customers["is_prime"].to_numpy(dtype=float)

    # Allocate the exact order target across the full year with trend, weekend,
    # festival-season, and random demand effects.
    order_days = pd.date_range(start.normalize(), end.normalize(), freq="D")
    day_number = np.arange(len(order_days))
    demand_weights = 0.86 + 0.28 * day_number / max(1, len(order_days) - 1)
    demand_weights *= np.where(order_days.dayofweek >= 5, 1.16, 1.0)
    demand_weights *= np.where(order_days.month.isin([10, 11, 12]), 1.12, 1.0)
    demand_weights *= rng.lognormal(mean=0.0, sigma=0.055, size=len(order_days))
    raw_quotas = demand_weights / demand_weights.sum() * config.n_orders
    day_quotas = np.floor(raw_quotas).astype(int)
    remaining_orders = config.n_orders - int(day_quotas.sum())
    if remaining_orders > 0:
        remainder_order = np.argsort(raw_quotas - day_quotas)[-remaining_orders:]
        day_quotas[remainder_order] += 1
    planned_order_days = np.repeat(order_days.to_numpy(), day_quotas)
    control_conversions = int(round(config.n_orders * 0.28 / (0.28 + 0.32)))
    experiment_plan = np.array(
        ["Control"] * control_conversions
        + ["Treatment"] * (config.n_orders - control_conversions),
        dtype=object,
    )
    rng.shuffle(experiment_plan)

    order_rows: list[dict] = []
    item_rows: list[dict] = []
    sold_by_day_store_product: dict[tuple, int] = defaultdict(int)
    item_id = 1

    current_day: pd.Timestamp | None = None
    daily_customer_iterator = iter(())
    for planned_day in planned_order_days:
        day = pd.Timestamp(planned_day)
        if current_day is None or day != current_day:
            current_day = day
            quota_index = (day - start.normalize()).days
            daily_quota = int(day_quotas[quota_index])
            eligible_mask = (
                active_customers
                & (signup_timestamps <= day.to_datetime64())
                & (available_after <= day.to_datetime64())
            )
            eligible = np.flatnonzero(eligible_mask)
            if len(eligible) < daily_quota:
                # This fallback protects unusually small custom simulations. It
                # preserves signup eligibility but relaxes repeat-gap constraints.
                eligible = np.flatnonzero(
                    active_customers & (signup_timestamps <= day.to_datetime64())
                )
            if len(eligible) < daily_quota:
                raise RuntimeError(
                    f"Only {len(eligible)} customers are available for {daily_quota} orders on {day.date()}."
                )
            selection_weights = 0.25 + customer_hidden["loyalty"][eligible]
            selection_weights += prime_flags[eligible] * 0.18
            selection_weights = selection_weights / selection_weights.sum()
            daily_customers = rng.choice(
                eligible,
                size=daily_quota,
                replace=False,
                p=selection_weights,
            )
            daily_customer_iterator = iter(daily_customers)
        customer_index = int(next(daily_customer_iterator))
        order_ts = _order_time_for_day(day, rng)

        customer = customers.iloc[customer_index]
        candidate_stores = store_lookup[customer["city"]]
        store_index = int(rng.choice(candidate_stores))
        store = stores.iloc[store_index]
        order_number = len(order_rows) + 1
        order_id = f"O{order_number:010d}"
        first_order = order_count_by_customer[customer_index] == 0
        order_count_by_customer[customer_index] += 1

        item_count = int(np.clip(1 + rng.poisson(2.1), 1, 8))
        selected = rng.choice(len(products), size=item_count, replace=True, p=product_popularity)
        selected_products, quantities_from_duplicates = np.unique(selected, return_counts=True)
        gross_value = 0.0
        order_sold_entries: list[tuple[tuple, int]] = []
        for product_index, duplicate_quantity in zip(selected_products, quantities_from_duplicates):
            product = products.iloc[int(product_index)]
            quantity = int(duplicate_quantity + rng.binomial(1, 0.14))
            markdown_rate = float(rng.choice([0.0, 0.03, 0.05, 0.08], p=[0.48, 0.22, 0.20, 0.10]))
            unit_price = round(float(product["list_price"]) * (1 - markdown_rate), 2)
            item_discount = round(float(product["list_price"]) - unit_price, 2)
            item_rows.append(
                {
                    "order_item_id": item_id,
                    "order_id": order_id,
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "unit_selling_price": unit_price,
                    "unit_cost": float(product["unit_cost"]),
                    "item_discount": item_discount,
                }
            )
            item_id += 1
            gross_value += quantity * unit_price
            inventory_key = (order_ts.date(), store["store_id"], product["product_id"])
            sold_by_day_store_product[inventory_key] += quantity
            order_sold_entries.append((inventory_key, quantity))

        # Constrained conversion counts reconstruct an approximately balanced
        # randomized experiment even for small custom runs. Shuffling keeps the
        # assignment independent of customer and order characteristics.
        experiment_variant = str(experiment_plan[order_number - 1])
        rain_probability = 0.34 if order_ts.month in (6, 7, 8, 9) else 0.08
        weather = "Rainy" if rng.random() < rain_probability else ("Hot" if order_ts.month in (4, 5) and rng.random() < 0.45 else "Clear")
        distance_km = round(float(np.clip(rng.gamma(2.0, 1.15), 0.4, 8.5)), 2)
        rush_hour = order_ts.hour in (8, 9, 18, 19, 20, 21)
        weekend = order_ts.dayofweek >= 5
        delivery_minutes = (
            13.0
            + distance_km * 2.8
            + (5.5 if rush_hour else 0)
            + (3.0 if weekend else 0)
            + (7.5 if weather == "Rainy" else 0)
            + (2.5 if weather == "Hot" else 0)
        ) * float(store["delivery_speed_factor"]) + float(rng.normal(0, 3.8))
        delivery_minutes = round(max(9.0, delivery_minutes), 2)
        promised_minutes = 30

        cancellation_probability = 0.018 + max(0, delivery_minutes - 38) * 0.0023
        cancellation_probability += 0.012 if weather == "Rainy" else 0
        if rng.random() < cancellation_probability:
            status = "Cancelled"
            delivery_ts = None
            for inventory_key, quantity in order_sold_entries:
                sold_by_day_store_product[inventory_key] -= quantity
                if sold_by_day_store_product[inventory_key] == 0:
                    del sold_by_day_store_product[inventory_key]
        else:
            status = "Refunded" if rng.random() < (0.012 + 0.006 * weekend) else "Delivered"
            delivery_ts = order_ts + pd.Timedelta(minutes=delivery_minutes)

        discount_amount = 0.0
        campaign_id = None
        if first_order:
            discount_amount = min(100.0, gross_value * 0.25)
            campaign_id = "WELCOME25"
        elif weather == "Rainy" and rng.random() < 0.24:
            discount_amount = min(60.0, gross_value * 0.12)
            campaign_id = "MONSOON12"
        elif weekend and rng.random() < 0.20:
            discount_amount = min(50.0, gross_value * 0.10)
            campaign_id = "WEEKEND10"
        if experiment_variant == "Treatment":
            discount_amount += min(20.0, gross_value * 0.04)

        delivery_fee = 0.0 if bool(customer["is_prime"]) or gross_value >= 499 else 25.0
        packaging_fee = float(rng.choice([5, 7, 9, 12], p=[0.20, 0.38, 0.28, 0.14]))
        refund_amount = round(gross_value * float(rng.uniform(0.55, 1.0)), 2) if status == "Refunded" else 0.0
        estimated_delivery_cost = round(
            29.0 + distance_km * 4.2 + (8.0 if weather == "Rainy" else 0) + (4.0 if rush_hour else 0),
            2,
        )
        if status == "Cancelled":
            # Cancelled orders incur only an estimated picking/dispatch attempt cost.
            estimated_delivery_cost = round(estimated_delivery_cost * 0.25, 2)

        order_rows.append(
            {
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "store_id": store["store_id"],
                "order_ts": order_ts,
                "delivery_ts": delivery_ts,
                "status": status,
                "promised_minutes": promised_minutes,
                "delivery_minutes": None if status == "Cancelled" else delivery_minutes,
                "distance_km": distance_km,
                "weather": weather,
                "payment_method": rng.choice(["UPI", "Card", "Wallet", "COD"], p=[0.58, 0.22, 0.13, 0.07]),
                "campaign_id": campaign_id,
                "experiment_variant": experiment_variant,
                "gross_merchandise_value": round(gross_value, 2),
                "discount_amount": round(discount_amount, 2),
                "delivery_fee": delivery_fee,
                "packaging_fee": packaging_fee,
                "refund_amount": refund_amount,
                "estimated_delivery_cost": estimated_delivery_cost,
                "is_first_order": first_order,
            }
        )

        loyalty = float(customer_hidden["loyalty"][customer_index])
        churn_probability = 0.025 + (1 - loyalty) * 0.045
        gap_multiplier = 1.0
        if status == "Cancelled":
            churn_probability += 0.24
            gap_multiplier *= 2.2
        elif status == "Refunded":
            churn_probability += 0.16
            gap_multiplier *= 1.8
        elif delivery_minutes > 35:
            churn_probability += 0.13
            gap_multiplier *= 1.65
        if bool(customer["is_prime"]):
            churn_probability *= 0.72

        if rng.random() >= churn_probability:
            gap_days = float(rng.exponential(customer_hidden["base_gap_days"][customer_index]))
            next_ts = order_ts + pd.Timedelta(days=max(0.3, gap_days * gap_multiplier))
            available_after[customer_index] = next_ts.to_datetime64()
        else:
            active_customers[customer_index] = False

    return pd.DataFrame(order_rows), pd.DataFrame(item_rows), sold_by_day_store_product


def _make_sessions(
    rng: np.random.Generator,
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    rows: list[dict] = []
    session_number = 1
    device_choices = ["Android", "iOS", "Web"]
    device_probs = [0.67, 0.25, 0.08]

    for order in orders.itertuples(index=False):
        rows.append(
            {
                "session_id": f"SES{session_number:011d}",
                "customer_id": order.customer_id,
                "session_ts": pd.Timestamp(order.order_ts) - pd.Timedelta(seconds=int(rng.integers(90, 1_200))),
                "experiment_variant": order.experiment_variant,
                "viewed_product": True,
                "added_to_cart": True,
                "checkout_started": True,
                "converted": True,
                "order_id": order.order_id,
                "session_duration_seconds": int(rng.integers(180, 1_500)),
                "device_type": rng.choice(device_choices, p=device_probs),
            }
        )
        session_number += 1

    converted_counts = orders["experiment_variant"].value_counts().to_dict()
    target_rates = {"Control": 0.28, "Treatment": 0.32}
    start = pd.Timestamp(start_date)
    total_minutes = int((pd.Timestamp(end_date) + pd.Timedelta(days=1) - start).total_seconds() // 60)
    customer_ids = customers["customer_id"].to_numpy()

    for variant, target_rate in target_rates.items():
        converted = int(converted_counts.get(variant, 0))
        target_sessions = int(math.ceil(converted / target_rate))
        for _ in range(target_sessions - converted):
            viewed = bool(rng.random() < 0.93)
            added = bool(viewed and rng.random() < (0.49 if variant == "Control" else 0.54))
            checkout = bool(added and rng.random() < (0.47 if variant == "Control" else 0.53))
            rows.append(
                {
                    "session_id": f"SES{session_number:011d}",
                    "customer_id": rng.choice(customer_ids),
                    "session_ts": start + pd.Timedelta(minutes=int(rng.integers(0, total_minutes))),
                    "experiment_variant": variant,
                    "viewed_product": viewed,
                    "added_to_cart": added,
                    "checkout_started": checkout,
                    "converted": False,
                    "order_id": None,
                    "session_duration_seconds": int(rng.integers(20, 900)),
                    "device_type": rng.choice(device_choices, p=device_probs),
                }
            )
            session_number += 1
    return pd.DataFrame(rows)


def _make_marketing_spend(
    config: GeneratorConfig, rng: np.random.Generator
) -> pd.DataFrame:
    channel_cpc = {
        "Organic": 0.0,
        "Paid Search": 28.0,
        "Social": 18.0,
        "Referral": 45.0,
        "Partnership": 34.0,
        "Offline": 55.0,
    }
    rows: list[dict] = []
    for date in pd.date_range(config.start_date, config.end_date, freq="D"):
        seasonality = 1.22 if date.month in (10, 11, 12) else 1.0
        for city in CITIES:
            for channel in CHANNELS:
                impressions = int(rng.integers(2_000, 18_000) * seasonality)
                ctr = float(rng.uniform(0.012, 0.055)) if channel != "Organic" else float(rng.uniform(0.04, 0.09))
                clicks = int(impressions * ctr)
                spend = clicks * channel_cpc[channel] * float(rng.uniform(0.88, 1.15))
                rows.append(
                    {
                        "spend_date": date.date(),
                        "city": city,
                        "acquisition_channel": channel,
                        "campaign_id": f"{channel[:3].upper()}-{date:%Y%m}",
                        "impressions": impressions,
                        "clicks": clicks,
                        "spend": round(spend, 2),
                    }
                )
    return pd.DataFrame(rows)


def _write_inventory_csv(
    config: GeneratorConfig,
    rng: np.random.Generator,
    stores: pd.DataFrame,
    products: pd.DataFrame,
    sold_map: dict[tuple, int],
) -> int:
    output_path = config.output_dir / "fact_inventory_daily.csv"
    if config.inventory_days <= 0:
        pd.DataFrame(
            columns=[
                "inventory_date", "store_id", "product_id", "opening_stock",
                "units_received", "units_sold", "waste_units", "closing_stock",
                "stockout_minutes",
            ]
        ).to_csv(output_path, index=False)
        return 0

    end = pd.Timestamp(config.end_date)
    inventory_start = max(pd.Timestamp(config.start_date), end - pd.Timedelta(days=config.inventory_days - 1))
    wrote_header = False
    total_rows = 0
    perishable = products["shelf_life_days"].to_numpy() <= 14
    product_ids = products["product_id"].to_numpy()

    for date in pd.date_range(inventory_start, end, freq="D"):
        chunk: list[dict] = []
        weekend = date.dayofweek >= 5
        for store_id in stores["store_id"]:
            for product_index, product_id in enumerate(product_ids):
                sold = int(sold_map.get((date.date(), store_id, product_id), 0))
                opening = int(rng.integers(4, 24) + min(18, sold // 2))
                waste_rate = 0.055 if perishable[product_index] else 0.006
                waste = int(rng.binomial(opening, waste_rate))
                target_close = int(rng.integers(3, 18))
                received = max(0, sold + waste + target_close - opening)
                closing = opening + received - sold - waste
                pressure = sold / max(1, opening)
                stockout_probability = min(0.82, 0.025 + 0.20 * max(0, pressure - 0.7) + (0.08 if weekend else 0))
                stockout_minutes = int(rng.integers(20, 300)) if rng.random() < stockout_probability else 0
                chunk.append(
                    {
                        "inventory_date": date.date(),
                        "store_id": store_id,
                        "product_id": product_id,
                        "opening_stock": opening,
                        "units_received": received,
                        "units_sold": sold,
                        "waste_units": waste,
                        "closing_stock": closing,
                        "stockout_minutes": stockout_minutes,
                    }
                )
        pd.DataFrame(chunk).to_csv(
            output_path,
            mode="a" if wrote_header else "w",
            header=not wrote_header,
            index=False,
        )
        wrote_header = True
        total_rows += len(chunk)
    return total_rows


def generate_project_data(config: GeneratorConfig) -> dict:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config.seed)
    stores = _make_stores(rng)
    products = _make_products(rng)
    customers, customer_hidden = _make_customers(config, rng)

    stores.to_csv(config.output_dir / "dim_stores.csv", index=False)
    products.to_csv(config.output_dir / "dim_products.csv", index=False)
    customers.to_csv(config.output_dir / "dim_customers.csv", index=False)

    orders, items, sold_map = _make_orders_and_items(
        config, rng, customers, customer_hidden, stores, products
    )
    orders.to_csv(config.output_dir / "fact_orders.csv", index=False)
    items.to_csv(config.output_dir / "fact_order_items.csv", index=False)
    item_count = len(items)
    del items

    # Materialise inventory before sessions so the large sold-unit lookup can be released.
    inventory_count = _write_inventory_csv(config, rng, stores, products, sold_map)
    del sold_map

    sessions = _make_sessions(rng, orders, customers, config.start_date, config.end_date)
    sessions.to_csv(config.output_dir / "fact_sessions.csv", index=False)
    session_count = len(sessions)
    del sessions

    marketing = _make_marketing_spend(config, rng)
    marketing.to_csv(config.output_dir / "fact_marketing_spend.csv", index=False)
    marketing_count = len(marketing)
    del marketing

    metadata = {
        "project": "Quick-Commerce Profitability & Retention Analytics",
        "synthetic_data": True,
        "seed": config.seed,
        "date_range": [config.start_date, config.end_date],
        "row_counts": {
            "dim_customers": len(customers),
            "dim_stores": len(stores),
            "dim_products": len(products),
            "fact_orders": len(orders),
            "fact_order_items": item_count,
            "fact_sessions": session_count,
            "fact_inventory_daily": inventory_count,
            "fact_marketing_spend": marketing_count,
        },
        "embedded_patterns_to_validate": [
            "Treatment sessions have about four percentage points higher conversion.",
            "Late, cancelled, and refunded orders reduce 30-day repeat behaviour.",
            "Rain, rush hours, distance, and store performance affect delivery time.",
            "Discounts can lift conversion while eroding contribution margin.",
            "Perishable products have greater inventory waste.",
        ],
    }
    with (config.output_dir / "generation_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the synthetic quick-commerce dataset.")
    parser.add_argument("--orders", type=int, default=250_000, help="Exact number of orders to generate.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inventory-days", type=int, default=365, help="Use 0 to skip inventory rows.")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = GeneratorConfig(
        n_orders=args.orders,
        seed=args.seed,
        inventory_days=args.inventory_days,
        output_dir=args.output_dir or RAW_DATA_DIR,
    )
    metadata = generate_project_data(config)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

