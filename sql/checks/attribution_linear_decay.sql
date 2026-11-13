select credited_channel,
       round(sum(if(model = 'first_touch', attributed_revenue_usd, 0))) as first_touch,
       round(sum(if(model = 'last_touch', attributed_revenue_usd, 0))) as last_touch,
       round(sum(if(model = 'linear', attributed_revenue_usd, 0))) as linear,
       round(sum(if(model = 'time_decay', attributed_revenue_usd, 0))) as time_decay
from `da02-customer360.marts.fct_attribution_by_channel`
group by credited_channel order by linear desc;