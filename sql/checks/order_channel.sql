select ga4_match_status, order_channel, count(*) as orders,
       round(sum(net_revenue_usd), 0) as net_revenue_usd,
       countif(is_first_order) as first_orders
from `da02-customer360.marts.fct_orders`
group by ga4_match_status, order_channel
order by orders desc