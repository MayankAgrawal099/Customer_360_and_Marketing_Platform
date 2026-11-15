-- Tableau extract: one row per CRM order, for the customer profile page (order timeline and order list).
select
    order_id,
    customer_id,
    order_date,
    order_channel,
    status,
    is_refunded,
    order_number,
    is_first_order,
    item_count,
    order_value_usd,
    refund_usd,
    net_revenue_usd,
    days_since_previous_order,
    ga4_match_status,
    purchase_channel_group
from `da02-customer360.marts.fct_orders`
