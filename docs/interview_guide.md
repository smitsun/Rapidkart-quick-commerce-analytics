# Interview and Presentation Guide

## 90-second opening

“I built an end-to-end profitability and retention analytics system for a fictional quick-commerce company. The business problem was that GMV alone could hide margin leakage. I generated a reproducible dataset, modelled it in PostgreSQL, added quality checks, and used SQL, Python, statistics, and Power BI to connect delivery performance, retention, product economics, inventory, and experiment results. My recommendations compare financial impact and customer impact rather than reporting vanity metrics.”

## Suggested eight-minute walkthrough

1. **Problem — 45 seconds:** State the decision, not the tool stack.
2. **Model — 60 seconds:** Explain each fact table's grain and the star schema.
3. **Quality — 45 seconds:** Show GMV reconciliation, keys, funnel logic, and inventory balance.
4. **Executive result — 90 seconds:** Explain margin and the weakest stores/categories.
5. **Customer result — 90 seconds:** Explain cohort/RFM and the late-delivery repeat gap.
6. **Experiment — 90 seconds:** Explain random assignment, lift, p-value, and discount cost.
7. **Action — 60 seconds:** Recommend actions, owners, and success metrics.
8. **Limitations — 30 seconds:** Clearly disclose synthetic data and next validation steps.

## Questions you should be ready to answer

- Why is GMV different from revenue and contribution margin?
- What is the grain of every table?
- Why did you use a star schema?
- How did you prevent double-counting after joining orders and items?
- Why can the late-delivery analysis show association but not prove causation?
- What assumptions are required for the A/B test?
- Why can a statistically significant experiment still be a bad launch?
- How would you calculate incremental profit from the treatment?
- How would you handle late-arriving facts and slowly changing dimensions?
- Which indexes improve the SQL queries and why?
- How would you monitor this pipeline in production?
- How would you backtest the demand forecast?

## Resume bullets after running the full dataset

- Built a reproducible quick-commerce analytics platform covering 250K orders and 2M+ related records using PostgreSQL, Python, Power BI, and automated data-quality checks.
- Developed advanced SQL models for contribution margin, cohort retention, RFM segmentation, funnel conversion, inventory availability, and channel CAC.
- Evaluated a simulated checkout experiment using a two-proportion significance test and quantified the trade-off between conversion lift and promotional cost.
- Produced a stakeholder dashboard and executive memo linking service performance to 30-day repeat behaviour and store-level margin risk.

Do not quote a financial “impact” unless you calculate it from your generated run and explain that it is simulated.

