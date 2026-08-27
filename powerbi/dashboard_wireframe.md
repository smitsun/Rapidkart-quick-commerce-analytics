# Dashboard Wireframe

## Page 1 — Executive Overview

```text
+------------------------------------------------------------------+
| Date | City | Store | Membership                                  |
+------------+------------+------------+-----------------------------+
| GMV        | Net Revenue| Contr. Mgn | Margin %                    |
+------------+------------+------------+-----------------------------+
| Revenue and margin trend          | City margin vs delivery time  |
|                                   |                               |
+-----------------------------------+-------------------------------+
| Store exception table: margin, cancellation, on-time, repeat      |
+------------------------------------------------------------------+
```

Decision: identify locations requiring margin or service intervention.

## Page 2 — Customer & Retention

- KPI cards: purchasing customers, repeat rate, AOV, estimated CAC
- Cohort-retention heatmap
- RFM-segment distribution
- 30-day repeat rate by service outcome
- Acquisition-channel CAC versus customer contribution scatterplot

Decision: choose retention and acquisition priorities.

## Page 3 — Store Operations

- Store/zone selector and map or matrix
- On-time rate, average delivery time, cancellation rate
- Hour-by-weekday order heatmap
- Weather and rush-hour service breakdown
- Actual order trend and 28-day forecast
- Drill-through table for store-week exceptions

Decision: allocate capacity and investigate weak service zones.

## Page 4 — Product & Inventory

- Category revenue and gross-profit waterfall
- Product margin-versus-volume scatterplot
- Stockout minutes by category/store
- Waste rate by category
- Top products requiring replenishment or assortment review

Decision: distinguish availability opportunities from low-margin or high-waste products.

## Interaction rules

- Keep no more than six visuals on a page.
- Every page must have a written “So what?” insight box.
- Use red only for an exception requiring action.
- Default to contribution margin, not GMV.
- Put definitions in a tooltip/help panel.

