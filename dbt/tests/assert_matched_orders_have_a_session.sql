-- A matched web order must point to a real session, and that session's device, if identity resolution
-- linked it to a customer, must be linked to the SAME customer that placed the order.
select o.order_id
from {{ ref('fct_orders') }} as o
left join {{ ref('fct_sessions') }} as s on s.session_key = o.ga_session_key
where (o.ga4_match_status = 'matched' and (s.session_key is null or o.purchase_channel_group is null or not s.is_converted))
   or (o.ga4_match_status != 'matched' and o.ga_session_key is not null)
   or (s.customer_id is not null and s.customer_id != o.customer_id)
   or (o.ga4_match_status = 'matched' and abs(o.ga_revenue_usd - o.order_value_usd) > 0.01)
