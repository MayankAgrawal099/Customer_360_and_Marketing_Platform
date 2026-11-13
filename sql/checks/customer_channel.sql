select count(*) as customers, countif(is_buyer) as buyers, countif(is_repeat_buyer) as repeat_buyers,
       countif(has_linked_device) as with_device, countif(sessions > 0) as with_sessions,
       round(sum(net_revenue_usd), 2) as net_revenue
from `da02-customer360.marts.dim_customers`;