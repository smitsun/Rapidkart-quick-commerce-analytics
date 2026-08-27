# Verified Sample Findings

These results come from the automated 25,000-order scale check with seed 42 and 30 inventory days. They demonstrate that the pipeline works; rerun the full 250,000-order build before publishing final portfolio screenshots.

## Validation

- Date coverage: 1 January–31 December 2025, all 12 months
- Data-quality checks: 38 passed, 0 failed
- Orders: 25,000
- Order items: 76,321
- App sessions: 83,334
- Inventory rows: 86,400

## Executive metrics

- Placed GMV: INR 17.44 million
- Net revenue: INR 16.56 million
- Contribution margin: INR 3.48 million
- Contribution-margin rate: 21.0%
- Cancellation rate: 2.1%
- On-time rate: 70.1%

## Retention signal

- On-time (within 35 minutes) 30-day repeat rate: 50.5%
- Late-delivery 30-day repeat rate: 36.7%
- Absolute gap: 13.8 percentage points

This is an association in a synthetic simulation. It demonstrates the analytical method and is not a causal finding about a real company.

## Experiment decision

| Metric | Control | Treatment |
|---|---:|---:|
| Assigned sessions | 41,668 | 41,666 |
| Conversion rate | 28.0% | 32.0% |
| Average discount per conversion | INR 18.57 | INR 34.55 |
| Average margin per conversion | INR 147.52 | INR 132.20 |
| Contribution margin per assigned session | INR 41.30 | INR 42.30 |

The treatment creates statistically significant conversion lift and slightly higher contribution per assigned session, despite weaker margin per conversion. The simulated recommendation is a monitored rollout with a margin-per-session guardrail.

## Operational exception

The lowest-contribution stores in this sample are in Chennai. OMR has the lowest contribution margin, while Anna Nagar combines weak contribution with an on-time rate near 63%, making it a sensible candidate for a root-cause review of capacity, traffic windows, and inventory availability.
