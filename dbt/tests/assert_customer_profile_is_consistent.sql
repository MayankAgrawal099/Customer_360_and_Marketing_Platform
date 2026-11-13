-- Every CRM customer appears once, and the profile's own columns agree with each other.
select customer_id from {{ ref('dim_customers') }}
where (is_buyer != (orders > 0))
   or (is_buyer and (first_order_date is null or last_order_date < first_order_date or first_order_channel is null))
   or (not is_buyer and (first_order_date is not null or net_revenue_usd != 0 or avg_order_value_usd is not null))
   or refunded_orders > orders
   or abs(net_revenue_usd - (gross_revenue_usd - refund_usd)) > 0.01
   or has_linked_device != (linked_devices > 0)
   or (sessions > 0 and not has_linked_device)
   or (sessions = 0 and first_session_date is not null)
   or converted_sessions > sessions
   or (sessions > 0 and last_session_date < first_session_date)
union all
select 'missing: ' || c.customer_id from {{ ref('stg_crm__customers') }} as c
left join {{ ref('dim_customers') }} as p on p.customer_id = c.customer_id
where p.customer_id is null
