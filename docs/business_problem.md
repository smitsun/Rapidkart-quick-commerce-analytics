# Business Problem

## Company

RapidKart is a fictional quick-commerce company operating 24 dark stores across Bengaluru, Mumbai, Delhi NCR, Hyderabad, Pune, and Chennai.

## Management concern

GMV is growing, but leadership does not know whether that growth creates sustainable contribution margin. Customer complaints about delivery times have also increased, marketing spend is difficult to compare across channels, and the product team wants to launch a checkout discount treatment.

## Decisions to support

1. Which cities, stores, and products create or destroy contribution margin?
2. Which service outcomes are associated with weaker 30-day repeat behaviour?
3. Should the checkout treatment be launched?
4. Which acquisition channels deserve more or less budget?
5. Where are stockouts and waste creating operational risk?
6. What order volume should operations plan for during the next four weeks?

## KPI definitions

- **Placed GMV:** Selling value of ordered items before order-level discounts, fees, refunds, or cancellations.
- **Net revenue:** Zero for cancelled orders; otherwise GMV − order discount + delivery fee + packaging fee − refund amount.
- **Contribution margin:** Net revenue − realised item COGS − estimated delivery/attempt cost. Cancelled orders have zero realised COGS.
- **On-time rate:** Non-cancelled orders delivered within the promised time.
- **30-day repeat rate:** Eligible orders followed by another order from the same customer within 30 days.
- **Conversion rate:** Sessions resulting in an order divided by assigned sessions.
- **CAC:** Marketing spend divided by customers acquired during the analysis period.
- **Waste rate:** Waste units divided by units sold plus waste units.

## Acceptance criteria

- Every KPI has an explicit definition.
- Order GMV reconciles to order-item selling value.
- Primary and foreign keys pass validation.
- Funnel stages are logically ordered.
- Experiment lift includes a significance test.
- Recommendations state both expected benefit and risk.
- Synthetic data is clearly disclosed everywhere it matters.
