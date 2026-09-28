# Executive Summary

## Decision context

Management asked where profitability and retention are leaking and whether the checkout treatment should be launched.

## Findings

- The dataset contains 250,000 orders from 45,066 purchasing customers.
- Total contribution margin is INR 34,957,293, a 21.1% margin rate.
- Orders delivered within 35 minutes have a 50.3% 30-day repeat rate versus 37.2% for late orders, a 13.2% absolute gap.
- Treatment conversion is 32.0% versus 28.0% for control (two-sided p-value 0).
- Treatment contribution margin per assigned session is INR 42.45 versus INR 41.45 for control.
- Adyar, Chennai has the lowest simulated contribution margin at INR 770,052.

## Recommendations

1. Prioritise late-delivery reduction in the weakest service zones and monitor the 30-day repeat rate as the outcome metric.
2. Based on both statistical significance and contribution per assigned session, **launch the treatment with monitoring**; retain a margin guardrail after rollout.
3. Review products with high stockout minutes and positive gross profit separately from products with high waste and weak margins.

## Important limitation

This is synthetic portfolio data. The analysis demonstrates a reproducible method and must not be presented as evidence about a real company.
