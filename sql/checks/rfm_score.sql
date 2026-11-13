select r_score, count(*) as buyers, min(recency_days) as min_days, max(recency_days) as max_days,
       round(avg(monetary_usd), 2) as avg_spend
from `da02-customer360.marts.fct_customer_rfm`
group by r_score order by r_score;


select f_score, count(*) as buyers, round(sum(monetary_usd), 2) as net_revenue
from `da02-customer360.marts.fct_customer_rfm`
group by f_score order by f_score;