select model, credited_channel, round(attributed_orders) as orders,
       round(attributed_revenue_usd, 2) as net_revenue, round(share_of_revenue * 100, 1) as pct_revenue
from `da02-customer360.marts.fct_attribution_by_channel`
order by credited_channel, model;


select first_and_last_differ, count(*) as orders, round(sum(net_revenue_usd), 2) as net_revenue,
       round(avg(touchpoints), 1) as avg_touchpoints
from `da02-customer360.marts.fct_attribution_journeys`
group by first_and_last_differ;