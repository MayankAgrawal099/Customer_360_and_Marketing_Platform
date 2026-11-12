-- Every valid purchase must land in a session, and no revenue may be added or lost on the way.
with p as (
    select count(*) as purchases, sum(revenue_usd) as revenue from {{ ref('stg_ga4__purchases') }}
),
s as (
    select sum(valid_purchases) as purchases, sum(revenue_usd) as revenue from {{ ref('fct_sessions') }}
)
select p.purchases as purchases_staging, s.purchases as purchases_sessions,
       p.revenue as revenue_staging, s.revenue as revenue_sessions
from p, s
where p.purchases != s.purchases or abs(p.revenue - s.revenue) > 0.01
