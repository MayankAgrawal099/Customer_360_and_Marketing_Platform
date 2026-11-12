-- A refunded order is refunded in full; a completed order has no refund. Returns the orders that break this.
select order_id, status, order_value_usd, refund_usd
from {{ ref('stg_crm__orders') }}
where (status = 'refunded' and abs(refund_usd - order_value_usd) > 0.005)
   or (status = 'completed' and refund_usd != 0)
