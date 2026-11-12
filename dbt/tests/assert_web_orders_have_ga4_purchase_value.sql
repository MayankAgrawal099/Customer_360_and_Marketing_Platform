-- A web order that carries a GA4 transaction id must have the same value as that purchase.
select o.order_id, o.order_value_usd, p.revenue_usd
from {{ ref('stg_crm__orders') }} o
join {{ ref('stg_ga4__purchases') }} p on p.transaction_id = o.ga_transaction_id
where o.order_channel = 'web' and abs(o.order_value_usd - p.revenue_usd) > 0.01
