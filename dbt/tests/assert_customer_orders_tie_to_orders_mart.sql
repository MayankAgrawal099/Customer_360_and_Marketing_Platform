-- The profile must carry exactly the orders and money of the orders mart: nothing lost, nothing doubled.
with mart as (
    select count(*) as orders, sum(order_value_usd) as gross, sum(refund_usd) as refunds, sum(net_revenue_usd) as net
    from {{ ref('fct_orders') }}
),
profile as (
    select sum(orders) as orders, sum(gross_revenue_usd) as gross, sum(refund_usd) as refunds,
           sum(net_revenue_usd) as net, sum(web_orders + app_orders) as channel_orders
    from {{ ref('dim_customers') }}
)
select mart.orders as orders_mart, profile.orders as orders_profile
from mart, profile
where mart.orders != profile.orders
   or profile.channel_orders != profile.orders
   or abs(mart.gross - profile.gross) > 0.01
   or abs(mart.refunds - profile.refunds) > 0.01
   or abs(mart.net - profile.net) > 0.01
