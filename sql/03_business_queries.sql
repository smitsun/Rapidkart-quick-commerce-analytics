-- 25 portfolio-ready business questions.
-- Run after 00_schema.sql, loading data, 01_views.sql, and 02_indexes.sql.
SET search_path TO qcommerce;

-- 01. What is the executive KPI snapshot?
SELECT
    COUNT(*) AS orders,
    COUNT(DISTINCT customer_id) AS customers,
    ROUND(SUM(gross_merchandise_value), 2) AS gmv,
    ROUND(SUM(net_revenue), 2) AS net_revenue,
    ROUND(SUM(contribution_margin), 2) AS contribution_margin,
    ROUND(SUM(contribution_margin) / NULLIF(SUM(net_revenue), 0), 4) AS margin_rate,
    ROUND(AVG((status = 'Cancelled')::int), 4) AS cancellation_rate
FROM vw_order_economics;

-- 02. Which cities create value, not merely revenue?
SELECT
    s.city,
    COUNT(*) AS orders,
    ROUND(SUM(e.gross_merchandise_value), 2) AS gmv,
    ROUND(SUM(e.contribution_margin), 2) AS contribution_margin,
    ROUND(SUM(e.contribution_margin) / NULLIF(SUM(e.net_revenue), 0), 4) AS margin_rate
FROM vw_order_economics e
JOIN dim_stores s USING (store_id)
GROUP BY s.city
ORDER BY contribution_margin DESC;

-- 03. Which stores combine weak margins with poor delivery performance?
SELECT
    e.store_id,
    s.city,
    s.zone,
    COUNT(*) AS orders,
    ROUND(SUM(e.contribution_margin), 2) AS contribution_margin,
    ROUND(AVG(e.delivery_minutes) FILTER (WHERE e.status <> 'Cancelled'), 2) AS avg_delivery_minutes,
    ROUND(AVG(e.is_on_time::int) FILTER (WHERE e.status <> 'Cancelled'), 4) AS on_time_rate
FROM vw_order_economics e
JOIN dim_stores s USING (store_id)
GROUP BY e.store_id, s.city, s.zone
ORDER BY contribution_margin, on_time_rate;

-- 04. Which product categories contribute the most gross profit?
SELECT
    p.category,
    SUM(i.quantity) AS units,
    ROUND(SUM(i.quantity * i.unit_selling_price), 2) AS item_revenue,
    ROUND(SUM(i.quantity * (i.unit_selling_price - i.unit_cost)), 2) AS gross_profit
FROM fact_order_items i
JOIN dim_products p USING (product_id)
JOIN fact_orders o USING (order_id)
WHERE o.status <> 'Cancelled'
GROUP BY p.category
ORDER BY gross_profit DESC;

-- 05. Which products generate revenue but have weak unit economics?
SELECT
    product_id,
    category,
    subcategory,
    units,
    ROUND(item_revenue, 2) AS item_revenue,
    ROUND(gross_profit, 2) AS gross_profit,
    ROUND(gross_profit / NULLIF(item_revenue, 0), 4) AS gross_margin_rate
FROM vw_product_kpis
WHERE item_revenue >= (SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY item_revenue) FROM vw_product_kpis)
ORDER BY gross_margin_rate
LIMIT 20;

-- 06. How does service outcome affect 30-day repeat behaviour?
SELECT
    CASE
        WHEN status = 'Cancelled' THEN 'Cancelled'
        WHEN status = 'Refunded' THEN 'Refunded'
        WHEN delivery_minutes > 35 THEN 'Late (>35m)'
        ELSE 'On time (<=35m)'
    END AS service_group,
    COUNT(*) AS eligible_orders,
    ROUND(AVG(repeated_within_30d::int), 4) AS repeat_30d_rate
FROM vw_customer_order_sequence
WHERE order_ts <= (SELECT MAX(order_ts) - INTERVAL '30 days' FROM fact_orders)
GROUP BY service_group
ORDER BY repeat_30d_rate DESC;

-- 07. Monthly acquisition-cohort retention matrix.
WITH activity AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', MIN(order_ts) OVER (PARTITION BY customer_id))::date AS cohort_month,
        DATE_TRUNC('month', order_ts)::date AS activity_month
    FROM fact_orders
    WHERE status <> 'Cancelled'
), indexed AS (
    SELECT *,
        (DATE_PART('year', AGE(activity_month, cohort_month)) * 12
         + DATE_PART('month', AGE(activity_month, cohort_month)))::int AS month_number
    FROM activity
), cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM indexed WHERE month_number = 0 GROUP BY cohort_month
)
SELECT
    i.cohort_month,
    i.month_number,
    COUNT(DISTINCT i.customer_id) AS active_customers,
    ROUND(COUNT(DISTINCT i.customer_id)::numeric / c.cohort_size, 4) AS retention_rate
FROM indexed i
JOIN cohort_sizes c USING (cohort_month)
GROUP BY i.cohort_month, i.month_number, c.cohort_size
ORDER BY i.cohort_month, i.month_number;

-- 08. RFM customer segmentation.
WITH customer_value AS (
    SELECT
        customer_id,
        (MAX(MAX(order_ts)) OVER ()::date - MAX(order_ts)::date) AS recency_days,
        COUNT(*) AS frequency,
        SUM(net_revenue) AS monetary
    FROM vw_order_economics
    WHERE status <> 'Cancelled'
    GROUP BY customer_id
), scored AS (
    SELECT *,
        6 - NTILE(5) OVER (ORDER BY recency_days) AS r_score,
        NTILE(5) OVER (ORDER BY frequency) AS f_score,
        NTILE(5) OVER (ORDER BY monetary) AS m_score
    FROM customer_value
)
SELECT
    CASE
        WHEN r_score + f_score + m_score >= 13 THEN 'Champions'
        WHEN r_score + f_score + m_score >= 10 THEN 'Loyal'
        WHEN r_score + f_score + m_score >= 7 THEN 'Needs Attention'
        ELSE 'At Risk'
    END AS segment,
    COUNT(*) AS customers,
    ROUND(AVG(monetary), 2) AS avg_customer_revenue
FROM scored
GROUP BY segment
ORDER BY avg_customer_revenue DESC;

-- 09. Do larger discounts improve order frequency enough to protect margin?
SELECT
    CASE
        WHEN discount_amount = 0 THEN 'No discount'
        WHEN discount_amount < 30 THEN 'INR 1-29'
        WHEN discount_amount < 60 THEN 'INR 30-59'
        ELSE 'INR 60+'
    END AS discount_band,
    COUNT(*) AS orders,
    ROUND(AVG(gross_merchandise_value), 2) AS aov,
    ROUND(AVG(contribution_margin), 2) AS avg_contribution_margin
FROM vw_order_economics
GROUP BY discount_band
ORDER BY MIN(discount_amount);

-- 10. What operational factors are associated with late delivery?
SELECT
    weather,
    CASE WHEN EXTRACT(ISODOW FROM order_ts) IN (6, 7) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    CASE WHEN EXTRACT(HOUR FROM order_ts) IN (8, 9, 18, 19, 20, 21) THEN 'Rush' ELSE 'Non-rush' END AS traffic_window,
    COUNT(*) AS orders,
    ROUND(AVG(delivery_minutes), 2) AS avg_delivery_minutes,
    ROUND(AVG((delivery_minutes > 35)::int), 4) AS late_rate
FROM fact_orders
WHERE status <> 'Cancelled'
GROUP BY weather, day_type, traffic_window
ORDER BY late_rate DESC;

-- 11. How does rain affect cost and customer experience?
SELECT
    weather,
    COUNT(*) AS orders,
    ROUND(AVG(delivery_minutes), 2) AS avg_delivery_minutes,
    ROUND(AVG(estimated_delivery_cost), 2) AS avg_delivery_cost,
    ROUND(AVG(contribution_margin), 2) AS avg_contribution_margin
FROM vw_order_economics
WHERE status <> 'Cancelled'
GROUP BY weather
ORDER BY avg_delivery_minutes DESC;

-- 12. Where are cancellation rates highest after controlling for volume?
SELECT
    s.city,
    s.zone,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE o.status = 'Cancelled') AS cancellations,
    ROUND(AVG((o.status = 'Cancelled')::int), 4) AS cancellation_rate
FROM fact_orders o
JOIN dim_stores s USING (store_id)
GROUP BY s.city, s.zone
HAVING COUNT(*) >= 100
ORDER BY cancellation_rate DESC;

-- 13. What is the experiment funnel by variant?
SELECT * FROM vw_experiment_results ORDER BY experiment_variant;

-- 14. What is the experiment lift and approximate standard error?
WITH results AS (
    SELECT experiment_variant, COUNT(*)::numeric AS n, SUM(converted::int)::numeric AS x
    FROM fact_sessions GROUP BY experiment_variant
), pivoted AS (
    SELECT
        MAX(n) FILTER (WHERE experiment_variant = 'Control') AS n_control,
        MAX(x) FILTER (WHERE experiment_variant = 'Control') AS x_control,
        MAX(n) FILTER (WHERE experiment_variant = 'Treatment') AS n_treatment,
        MAX(x) FILTER (WHERE experiment_variant = 'Treatment') AS x_treatment
    FROM results
)
SELECT
    ROUND(x_control / n_control, 4) AS control_rate,
    ROUND(x_treatment / n_treatment, 4) AS treatment_rate,
    ROUND(x_treatment / n_treatment - x_control / n_control, 4) AS absolute_lift,
    ROUND(
        SQRT(((x_control + x_treatment) / (n_control + n_treatment))
        * (1 - (x_control + x_treatment) / (n_control + n_treatment))
        * (1 / n_control + 1 / n_treatment)), 6
    ) AS pooled_standard_error
FROM pivoted;

-- 15. What is customer acquisition cost by channel?
WITH spend AS (
    SELECT city, acquisition_channel, SUM(spend) AS spend
    FROM fact_marketing_spend GROUP BY city, acquisition_channel
), acquired AS (
    SELECT city, acquisition_channel, COUNT(*) AS customers
    FROM dim_customers
    WHERE signup_date BETWEEN (SELECT MIN(order_ts)::date FROM fact_orders)
        AND (SELECT MAX(order_ts)::date FROM fact_orders)
    GROUP BY city, acquisition_channel
)
SELECT
    s.city,
    s.acquisition_channel,
    ROUND(s.spend, 2) AS spend,
    a.customers,
    ROUND(s.spend / NULLIF(a.customers, 0), 2) AS cac
FROM spend s
LEFT JOIN acquired a USING (city, acquisition_channel)
ORDER BY cac DESC NULLS LAST;

-- 16. Which acquisition channels have the best revenue-to-CAC relationship?
WITH value AS (
    SELECT c.acquisition_channel, COUNT(DISTINCT c.customer_id) AS customers,
           SUM(e.contribution_margin) AS contribution_margin
    FROM dim_customers c
    JOIN vw_order_economics e USING (customer_id)
    GROUP BY c.acquisition_channel
), spend AS (
    SELECT acquisition_channel, SUM(spend) AS spend
    FROM fact_marketing_spend GROUP BY acquisition_channel
)
SELECT
    v.acquisition_channel,
    v.customers,
    ROUND(v.contribution_margin / NULLIF(v.customers, 0), 2) AS margin_per_customer,
    ROUND(s.spend / NULLIF(v.customers, 0), 2) AS blended_cac,
    ROUND(v.contribution_margin / NULLIF(s.spend, 0), 2) AS margin_to_spend_ratio
FROM value v JOIN spend s USING (acquisition_channel)
ORDER BY margin_to_spend_ratio DESC NULLS LAST;

-- 17. Which stores and products lose the most availability time?
SELECT
    i.store_id,
    s.city,
    s.zone,
    i.product_id,
    p.category,
    SUM(i.stockout_minutes) AS stockout_minutes,
    SUM(i.units_sold) AS units_sold
FROM fact_inventory_daily i
JOIN dim_stores s USING (store_id)
JOIN dim_products p USING (product_id)
GROUP BY i.store_id, s.city, s.zone, i.product_id, p.category
ORDER BY stockout_minutes DESC
LIMIT 30;

-- 18. Which categories create the most inventory waste?
SELECT
    p.category,
    SUM(i.units_sold) AS units_sold,
    SUM(i.waste_units) AS waste_units,
    ROUND(SUM(i.waste_units)::numeric / NULLIF(SUM(i.units_sold + i.waste_units), 0), 4) AS waste_rate
FROM fact_inventory_daily i
JOIN dim_products p USING (product_id)
GROUP BY p.category
ORDER BY waste_rate DESC;

-- 19. Are weekend stockouts materially worse?
SELECT
    CASE WHEN EXTRACT(ISODOW FROM inventory_date) IN (6, 7) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    COUNT(*) FILTER (WHERE stockout_minutes > 0) AS stockout_product_days,
    ROUND(AVG(stockout_minutes), 2) AS avg_stockout_minutes,
    SUM(units_sold) AS units_sold
FROM fact_inventory_daily
GROUP BY day_type;

-- 20. Daily orders with 7-day rolling average and prior-week change.
WITH daily AS (
    SELECT order_ts::date AS order_date, COUNT(*) AS orders
    FROM fact_orders GROUP BY order_ts::date
)
SELECT
    order_date,
    orders,
    ROUND(AVG(orders) OVER (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS rolling_7d,
    orders - LAG(orders, 7) OVER (ORDER BY order_date) AS change_vs_prior_week
FROM daily
ORDER BY order_date;

-- 21. Simple weekday baseline for near-term capacity planning.
WITH daily AS (
    SELECT order_ts::date AS order_date, EXTRACT(ISODOW FROM order_ts) AS weekday, COUNT(*) AS orders
    FROM fact_orders
    GROUP BY order_ts::date, EXTRACT(ISODOW FROM order_ts)
)
SELECT weekday, ROUND(AVG(orders), 1) AS expected_orders, ROUND(STDDEV_SAMP(orders), 1) AS demand_stddev
FROM daily
GROUP BY weekday
ORDER BY weekday;

-- 22. Does payment method correlate with cancellation or order value?
SELECT
    payment_method,
    COUNT(*) AS orders,
    ROUND(AVG(gross_merchandise_value), 2) AS aov,
    ROUND(AVG((status = 'Cancelled')::int), 4) AS cancellation_rate,
    ROUND(SUM(contribution_margin), 2) AS contribution_margin
FROM vw_order_economics
GROUP BY payment_method
ORDER BY orders DESC;

-- 23. What share of margin comes from the top 20% of customers?
WITH customer_margin AS (
    SELECT customer_id, SUM(contribution_margin) AS margin
    FROM vw_order_economics GROUP BY customer_id
), ranked AS (
    SELECT *, NTILE(5) OVER (ORDER BY margin DESC) AS value_quintile
    FROM customer_margin
)
SELECT
    value_quintile,
    COUNT(*) AS customers,
    ROUND(SUM(margin), 2) AS contribution_margin,
    ROUND(SUM(margin) / NULLIF(SUM(SUM(margin)) OVER (), 0), 4) AS margin_share
FROM ranked
GROUP BY value_quintile
ORDER BY value_quintile;

-- 24. Which categories are associated with the highest refunded value?
SELECT
    p.category,
    COUNT(DISTINCT o.order_id) FILTER (WHERE o.status = 'Refunded') AS refunded_orders,
    ROUND(SUM(o.refund_amount * (i.quantity * i.unit_selling_price)
        / NULLIF(o.gross_merchandise_value, 0)) FILTER (WHERE o.status = 'Refunded'), 2) AS allocated_refund_value
FROM fact_orders o
JOIN fact_order_items i USING (order_id)
JOIN dim_products p USING (product_id)
GROUP BY p.category
ORDER BY allocated_refund_value DESC NULLS LAST;

-- 25. Which store-week combinations require an operational deep dive?
WITH weekly AS (
    SELECT
        DATE_TRUNC('week', order_ts)::date AS week_start,
        store_id,
        COUNT(*) AS orders,
        AVG((status = 'Cancelled')::int) AS cancellation_rate,
        AVG((delivery_minutes > 35)::int) FILTER (WHERE status <> 'Cancelled') AS late_rate,
        SUM(contribution_margin) AS contribution_margin
    FROM vw_order_economics
    GROUP BY DATE_TRUNC('week', order_ts)::date, store_id
), thresholds AS (
    SELECT
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY cancellation_rate) AS cancellation_p75,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY late_rate) AS late_p75,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY contribution_margin) AS margin_p25
    FROM weekly
)
SELECT w.*
FROM weekly w CROSS JOIN thresholds t
WHERE w.cancellation_rate >= t.cancellation_p75
   OR w.late_rate >= t.late_p75
   OR w.contribution_margin <= t.margin_p25
ORDER BY week_start DESC, contribution_margin;
