select segment, count(*) as customers, sum(historical_net_revenue_usd) as net_revenue,
       round(avg(clv_12m_usd), 2) as avg_clv_12m
from `da02-customer360.marts.fct_customer_segments`
group by segment order by min(segment_order);


select customer_id, segment, orders, historical_net_revenue_usd, recency_days, clv_12m_usd
from `da02-customer360.marts.fct_customer_segments`
order by clv_12m_usd desc limit 5;