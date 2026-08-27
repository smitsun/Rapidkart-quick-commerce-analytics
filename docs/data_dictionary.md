# Data Dictionary

## `dim_customers`

Grain: one row per customer.

| Column | Meaning |
|---|---|
| `customer_id` | Synthetic customer key |
| `signup_date` | Account acquisition date |
| `city` | Customer city |
| `acquisition_channel` | First-touch acquisition channel |
| `age_band` | Non-identifying age group |
| `is_prime` | Membership indicator |

## `dim_stores`

Grain: one row per dark store.

| Column | Meaning |
|---|---|
| `store_id` | Store key |
| `city`, `zone` | Store geography |
| `opened_date` | Simulated launch date |
| `capacity_orders_per_hour` | Planning capacity |
| `delivery_speed_factor` | Latent operational performance factor used by the simulator |

## `dim_products`

Grain: one row per product.

| Column | Meaning |
|---|---|
| `product_id` | Product key |
| `category`, `subcategory` | Merchandising hierarchy |
| `brand_tier` | Value, mass, or premium |
| `unit_cost` | Simulated procurement cost |
| `list_price` | Undiscounted selling price |
| `shelf_life_days` | Expected shelf life |

## `fact_orders`

Grain: one row per placed order.

| Column | Meaning |
|---|---|
| `order_id` | Order key |
| `customer_id`, `store_id` | Dimension foreign keys |
| `order_ts`, `delivery_ts` | Order and delivery timestamps |
| `status` | Delivered, Cancelled, or Refunded |
| `promised_minutes`, `delivery_minutes` | Service-level fields |
| `distance_km`, `weather` | Delivery context |
| `payment_method` | UPI, card, wallet, or COD |
| `campaign_id` | Applied order campaign, if any |
| `experiment_variant` | Random checkout experiment assignment |
| `gross_merchandise_value` | Sum of order-item selling value |
| `discount_amount` | Order-level promotion |
| `delivery_fee`, `packaging_fee` | Customer fees |
| `refund_amount` | Refunded value |
| `estimated_delivery_cost` | Simulated variable fulfilment cost; cancelled orders retain only an attempt cost |
| `is_first_order` | Customer's first generated order |

## `fact_order_items`

Grain: one row per distinct product within an order.

| Column | Meaning |
|---|---|
| `order_item_id` | Line key |
| `order_id`, `product_id` | Foreign keys |
| `quantity` | Units ordered |
| `unit_selling_price` | Price after item markdown |
| `unit_cost` | Cost captured at transaction time |
| `item_discount` | List price minus selling price per unit |

## `fact_sessions`

Grain: one row per app/web session.

| Column | Meaning |
|---|---|
| `session_id` | Session key |
| `customer_id` | Customer key |
| `session_ts` | Session start |
| `experiment_variant` | Control or Treatment |
| `viewed_product` | Reached product-view stage |
| `added_to_cart` | Reached cart stage |
| `checkout_started` | Reached checkout stage |
| `converted` | Resulted in an order |
| `order_id` | Order key for converted sessions |
| `session_duration_seconds` | Session duration |
| `device_type` | Android, iOS, or Web |

## `fact_inventory_daily`

Grain: one row per date, store, and product.

| Column | Meaning |
|---|---|
| `inventory_date`, `store_id`, `product_id` | Composite key |
| `opening_stock` | Units at start of day |
| `units_received` | Replenished units |
| `units_sold` | Units sold |
| `waste_units` | Expired or damaged units |
| `closing_stock` | Opening + received − sold − waste |
| `stockout_minutes` | Intraday minutes unavailable |

## `fact_marketing_spend`

Grain: one row per date, city, and acquisition channel.

| Column | Meaning |
|---|---|
| `spend_date`, `city`, `acquisition_channel` | Reporting dimensions |
| `campaign_id` | Monthly campaign key |
| `impressions`, `clicks` | Funnel activity |
| `spend` | Simulated INR media spend |
