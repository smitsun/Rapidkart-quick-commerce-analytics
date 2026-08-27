SET search_path TO qcommerce;

CREATE INDEX idx_orders_customer_ts ON fact_orders (customer_id, order_ts);
CREATE INDEX idx_orders_store_ts ON fact_orders (store_id, order_ts);
CREATE INDEX idx_orders_status ON fact_orders (status);
CREATE INDEX idx_order_items_order ON fact_order_items (order_id);
CREATE INDEX idx_order_items_product ON fact_order_items (product_id);
CREATE INDEX idx_sessions_variant ON fact_sessions (experiment_variant, converted);
CREATE INDEX idx_inventory_store_date ON fact_inventory_daily (store_id, inventory_date);
CREATE INDEX idx_inventory_product_date ON fact_inventory_daily (product_id, inventory_date);

