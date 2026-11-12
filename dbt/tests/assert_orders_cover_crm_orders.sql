-- No order may be lost, doubled or changed in value on the way to the orders mart.
with source as (
    select count(*) as orders, sum(order_value_usd) as value, sum(refund_usd) as refunds, sum(net_revenue_usd) as net
    from {{ ref('stg_crm__orders') }}
),
mart as (
    select count(*) as orders, sum(order_value_usd) as value, sum(refund_usd) as refunds, sum(net_revenue_usd) as net
    from {{ ref('fct_orders') }}
)
select source.orders as orders_staging, mart.orders as orders_mart,
       source.value as value_staging, mart.value as value_mart
from source, mart
where source.orders != mart.orders
   or abs(source.value - mart.value) > 0.01
   or abs(source.refunds - mart.refunds) > 0.01
   or abs(source.net - mart.net) > 0.01
