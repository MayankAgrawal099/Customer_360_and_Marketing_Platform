-- One row per synthetic CRM order. net_revenue_usd is what the business keeps: order value minus refunds.

select
    order_id,
    customer_id,
    order_ts,
    date(order_ts) as order_date,
    order_channel,
    ga_transaction_id,
    order_value_usd,
    item_count,
    status,
    refund_usd,
    status = 'refunded' as is_refunded,
    order_value_usd - refund_usd as net_revenue_usd
from {{ source('raw', 'crm_orders') }}
