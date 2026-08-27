# Power BI Model and Build Guide

## Connection

Preferred portfolio setup: connect Power BI Desktop to PostgreSQL on `localhost:5432`, database `quickcommerce`, and select tables/views from the `qcommerce` schema.

For a no-database demo, import the CSV files from `data/processed` after running `python -m src.analyze`.

## Relationships

Create one-directional relationships from dimensions to facts:

| From | Cardinality | To | Key |
|---|---:|---|---|
| `dim_customers` | 1:* | `fact_orders` | `customer_id` |
| `dim_customers` | 1:* | `fact_sessions` | `customer_id` |
| `dim_stores` | 1:* | `fact_orders` | `store_id` |
| `dim_stores` | 1:* | `fact_inventory_daily` | `store_id` |
| `dim_products` | 1:* | `fact_order_items` | `product_id` |
| `dim_products` | 1:* | `fact_inventory_daily` | `product_id` |
| `fact_orders` | 1:* | `fact_order_items` | `order_id` |
| `Date` | 1:* | `fact_orders` | `Date` → derived `order_date` |
| `Date` | 1:* | `fact_inventory_daily` | `Date` → `inventory_date` |

Keep relationships single-direction unless a documented visual requires otherwise. Avoid a direct active relationship from sessions to orders; customer and date context are sufficient for the funnel pages.

## Date table

Create:

```dax
Date =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2025, 1, 1 ), DATE ( 2026, 1, 31 ) ),
    "Year", YEAR ( [Date] ),
    "Month Number", MONTH ( [Date] ),
    "Month", FORMAT ( [Date], "MMM" ),
    "Year Month", FORMAT ( [Date], "YYYY-MM" ),
    "Weekday Number", WEEKDAY ( [Date], 2 ),
    "Weekday", FORMAT ( [Date], "DDD" ),
    "Is Weekend", WEEKDAY ( [Date], 2 ) >= 6
)
```

Mark it as the model's date table. Sort `Month` by `Month Number` and `Weekday` by `Weekday Number`.

## Import checklist

- Set currency fields to INR with no more than two decimals.
- Use whole numbers for orders, customers, units, and minutes where appropriate.
- Hide technical IDs from report view but keep them in the model.
- Disable automatic date/time.
- Add descriptions to measures.
- Place all measures in a dedicated `_Measures` table.
- Import `rapidkart_theme.json` before formatting visuals.

## Row-level security demonstration

Create a `UserAccess` table with `email` and `city`. Relate it to a distinct City dimension, then use:

```dax
UserAccess[email] = USERPRINCIPALNAME()
```

Explain that this is a portfolio demonstration and test at least two roles in “View as”.

## Verification

Before screenshots or recording, reconcile these Power BI results with:

- `outputs/executive_kpis.json`
- `data/processed/store_kpis.csv`
- `data/processed/experiment_summary.csv`
- `outputs/data_quality_report.json`

