SET search_path TO qcommerce;

CREATE OR REPLACE VIEW vw_order_economics AS
WITH item_costs AS (
    SELECT
        order_id,
        SUM(quantity * unit_selling_price) AS item_revenue,
        SUM(quantity * unit_cost) AS cogs,
        SUM(quantity) AS units
    FROM fact_order_items
    GROUP BY order_id
)
SELECT
    o.*,
    i.units,
    i.cogs,
    CASE WHEN o.status = 'Cancelled' THEN 0
        ELSE o.gross_merchandise_value - o.discount_amount
            + o.delivery_fee + o.packaging_fee - o.refund_amount
    END AS net_revenue,
    CASE WHEN o.status = 'Cancelled' THEN -o.estimated_delivery_cost
        ELSE o.gross_merchandise_value - o.discount_amount
            + o.delivery_fee + o.packaging_fee - o.refund_amount
            - i.cogs - o.estimated_delivery_cost
    END AS contribution_margin,
    CASE
        WHEN o.delivery_minutes <= o.promised_minutes THEN TRUE
        ELSE FALSE
    END AS is_on_time
FROM fact_orders o
JOIN item_costs i USING (order_id);

CREATE OR REPLACE VIEW vw_customer_order_sequence AS
SELECT
    customer_id,
    order_id,
    order_ts,
    delivery_minutes,
    status,
    LEAD(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts) AS next_order_ts,
    COALESCE(
        LEAD(order_ts) OVER (PARTITION BY customer_id ORDER BY order_ts) <= order_ts + INTERVAL '30 days',
        FALSE
    ) AS repeated_within_30d
FROM fact_orders;

CREATE OR REPLACE VIEW vw_daily_store_kpis AS
SELECT
    order_ts::date AS order_date,
    store_id,
    COUNT(*) AS orders,
    COUNT(*) FILTER (WHERE status = 'Delivered') AS delivered_orders,
    SUM(gross_merchandise_value) AS gmv,
    SUM(net_revenue) AS net_revenue,
    SUM(contribution_margin) AS contribution_margin,
    AVG(delivery_minutes) FILTER (WHERE status <> 'Cancelled') AS avg_delivery_minutes,
    AVG(is_on_time::int) FILTER (WHERE status <> 'Cancelled') AS on_time_rate,
    AVG((status = 'Cancelled')::int) AS cancellation_rate
FROM vw_order_economics
GROUP BY order_ts::date, store_id;

CREATE OR REPLACE VIEW vw_product_kpis AS
SELECT
    i.product_id,
    p.category,
    p.subcategory,
    SUM(i.quantity) AS units,
    SUM(i.quantity * i.unit_selling_price) AS item_revenue,
    SUM(i.quantity * (i.unit_selling_price - i.unit_cost)) AS gross_profit
FROM fact_order_items i
JOIN dim_products p USING (product_id)
JOIN fact_orders o USING (order_id)
WHERE o.status <> 'Cancelled'
GROUP BY i.product_id, p.category, p.subcategory;

CREATE OR REPLACE VIEW vw_experiment_results AS
SELECT
    experiment_variant,
    COUNT(*) AS sessions,
    COUNT(*) FILTER (WHERE converted) AS conversions,
    AVG(converted::int) AS conversion_rate,
    AVG(added_to_cart::int) AS add_to_cart_rate,
    AVG(checkout_started::int) AS checkout_rate
FROM fact_sessions
GROUP BY experiment_variant;
