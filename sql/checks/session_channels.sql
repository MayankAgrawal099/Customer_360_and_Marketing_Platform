select channel_group, count(*) as sessions, countif(is_converted) as converted,
       round(sum(revenue_usd), 0) as revenue_usd, countif(is_identified) as identified
from `da02-customer360.marts.fct_sessions`
group by channel_group
order by sessions desc