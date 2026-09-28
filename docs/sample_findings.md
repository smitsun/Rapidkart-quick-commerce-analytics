# Verified Full-Scale Findings

These results come from the reproducible portfolio build with seed 42, 250,000 orders, and 365 inventory days. The same build was loaded into PostgreSQL and all 25 documented business queries executed without errors.

## Validation

- Date coverage: 1 January-31 December 2025, all 12 months
- Data-quality checks: 38 passed, 0 failed
- Orders: 250,000
- Order items: 764,979
- App sessions: 833,334
- Inventory rows: 1,051,200
- PostgreSQL row counts: matched every generated table

## Executive metrics

- Placed GMV: INR 173.64 million
- Net revenue: INR 165.50 million
- Contribution margin: INR 34.96 million
- Contribution-margin rate: 21.1%
- Cancellation rate: 2.0%
- On-time rate: 70.3%

## Retention signal

- On-time (within 35 minutes) 30-day repeat rate: 50.3%
- Late-delivery 30-day repeat rate: 37.2%
- Absolute gap: 13.2 percentage points

This is an association embedded in a synthetic simulation. It demonstrates the analytical method and is not a causal finding about a real company.

## Experiment decision

| Metric | Control | Treatment |
|---|---:|---:|
| Assigned sessions | 416,668 | 416,666 |
| Conversion rate | 28.0% | 32.0% |
| Contribution margin per assigned session | INR 41.45 | INR 42.45 |

The treatment creates a statistically significant conversion lift and slightly higher contribution per assigned session despite the additional discount. The simulated recommendation is a monitored rollout with a margin-per-session guardrail.

## Operational exception

Adyar, Chennai has the lowest absolute contribution margin in the full build. Absolute contribution is affected by market size, so this should be reviewed alongside margin rate, order volume, delivery reliability, and local capacity before action is taken.

## Reproduce the result

```powershell
docker compose up -d
python -m src.pipeline --orders 250000 --inventory-days 365 --load-postgres --database-url "postgresql+psycopg2://analyst:analyst@localhost:5432/quickcommerce"
pytest
```

All company and customer data is synthetic. The findings demonstrate a reproducible analytical workflow, not real-world company performance.
