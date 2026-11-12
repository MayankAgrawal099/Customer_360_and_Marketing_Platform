-- Every order has exactly one Segment "Order Completed" event, carrying the same customer, value,
-- channel and status, and there are no such events without an order.
with tracks as (
    select order_id, customer_id, revenue_usd, order_channel, order_status
    from {{ ref('stg_segment__tracks') }}
    where event_name = 'Order Completed'
)
select coalesce(o.order_id, t.order_id) as order_id
from {{ ref('fct_orders') }} as o
full outer join tracks as t on t.order_id = o.order_id
where o.order_id is null
   or t.order_id is null
   or t.customer_id != o.customer_id
   or abs(t.revenue_usd - o.order_value_usd) > 0.01
   or t.order_channel != o.order_channel
   or t.order_status != o.status
