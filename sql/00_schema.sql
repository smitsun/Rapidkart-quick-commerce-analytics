-- Development schema for the portfolio project.
-- Only the dedicated qcommerce schema is recreated.
DROP SCHEMA IF EXISTS qcommerce CASCADE;
CREATE SCHEMA qcommerce;
SET search_path TO qcommerce;

CREATE TABLE dim_customers (
    customer_id VARCHAR(12) PRIMARY KEY,
    signup_date DATE NOT NULL,
    city VARCHAR(40) NOT NULL,
    acquisition_channel VARCHAR(30) NOT NULL,
    age_band VARCHAR(10) NOT NULL,
    is_prime BOOLEAN NOT NULL
);

CREATE TABLE dim_stores (
    store_id VARCHAR(10) PRIMARY KEY,
    city VARCHAR(40) NOT NULL,
    zone VARCHAR(40) NOT NULL,
    opened_date DATE NOT NULL,
    capacity_orders_per_hour INTEGER NOT NULL CHECK (capacity_orders_per_hour > 0),
    delivery_speed_factor NUMERIC(5,3) NOT NULL CHECK (delivery_speed_factor > 0)
);

CREATE TABLE dim_products (
    product_id VARCHAR(10) PRIMARY KEY,
    category VARCHAR(40) NOT NULL,
    subcategory VARCHAR(60) NOT NULL,
    brand_tier VARCHAR(20) NOT NULL,
    unit_cost NUMERIC(10,2) NOT NULL CHECK (unit_cost >= 0),
    list_price NUMERIC(10,2) NOT NULL CHECK (list_price >= unit_cost),
    shelf_life_days INTEGER NOT NULL CHECK (shelf_life_days > 0)
);

CREATE TABLE fact_orders (
    order_id VARCHAR(14) PRIMARY KEY,
    customer_id VARCHAR(12) NOT NULL REFERENCES dim_customers(customer_id),
    store_id VARCHAR(10) NOT NULL REFERENCES dim_stores(store_id),
    order_ts TIMESTAMP NOT NULL,
    delivery_ts TIMESTAMP,
    status VARCHAR(12) NOT NULL CHECK (status IN ('Delivered', 'Cancelled', 'Refunded')),
    promised_minutes INTEGER NOT NULL,
    delivery_minutes NUMERIC(8,2),
    distance_km NUMERIC(8,2) NOT NULL,
    weather VARCHAR(12) NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    campaign_id VARCHAR(20),
    experiment_variant VARCHAR(12) NOT NULL CHECK (experiment_variant IN ('Control', 'Treatment')),
    gross_merchandise_value NUMERIC(12,2) NOT NULL,
    discount_amount NUMERIC(12,2) NOT NULL,
    delivery_fee NUMERIC(10,2) NOT NULL,
    packaging_fee NUMERIC(10,2) NOT NULL,
    refund_amount NUMERIC(12,2) NOT NULL,
    estimated_delivery_cost NUMERIC(10,2) NOT NULL,
    is_first_order BOOLEAN NOT NULL
);

CREATE TABLE fact_order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id VARCHAR(14) NOT NULL REFERENCES fact_orders(order_id),
    product_id VARCHAR(10) NOT NULL REFERENCES dim_products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_selling_price NUMERIC(10,2) NOT NULL CHECK (unit_selling_price >= 0),
    unit_cost NUMERIC(10,2) NOT NULL CHECK (unit_cost >= 0),
    item_discount NUMERIC(10,2) NOT NULL CHECK (item_discount >= 0)
);

CREATE TABLE fact_sessions (
    session_id VARCHAR(16) PRIMARY KEY,
    customer_id VARCHAR(12) NOT NULL REFERENCES dim_customers(customer_id),
    session_ts TIMESTAMP NOT NULL,
    experiment_variant VARCHAR(12) NOT NULL CHECK (experiment_variant IN ('Control', 'Treatment')),
    viewed_product BOOLEAN NOT NULL,
    added_to_cart BOOLEAN NOT NULL,
    checkout_started BOOLEAN NOT NULL,
    converted BOOLEAN NOT NULL,
    order_id VARCHAR(14) REFERENCES fact_orders(order_id),
    session_duration_seconds INTEGER NOT NULL CHECK (session_duration_seconds > 0),
    device_type VARCHAR(12) NOT NULL
);

CREATE TABLE fact_inventory_daily (
    inventory_date DATE NOT NULL,
    store_id VARCHAR(10) NOT NULL REFERENCES dim_stores(store_id),
    product_id VARCHAR(10) NOT NULL REFERENCES dim_products(product_id),
    opening_stock INTEGER NOT NULL CHECK (opening_stock >= 0),
    units_received INTEGER NOT NULL CHECK (units_received >= 0),
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    waste_units INTEGER NOT NULL CHECK (waste_units >= 0),
    closing_stock INTEGER NOT NULL CHECK (closing_stock >= 0),
    stockout_minutes INTEGER NOT NULL CHECK (stockout_minutes BETWEEN 0 AND 1440),
    PRIMARY KEY (inventory_date, store_id, product_id)
);

CREATE TABLE fact_marketing_spend (
    spend_date DATE NOT NULL,
    city VARCHAR(40) NOT NULL,
    acquisition_channel VARCHAR(30) NOT NULL,
    campaign_id VARCHAR(20) NOT NULL,
    impressions INTEGER NOT NULL CHECK (impressions >= 0),
    clicks INTEGER NOT NULL CHECK (clicks >= 0),
    spend NUMERIC(12,2) NOT NULL CHECK (spend >= 0),
    PRIMARY KEY (spend_date, city, acquisition_channel)
);

