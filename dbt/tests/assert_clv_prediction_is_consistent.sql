-- The prediction must follow its own recipe: horizons scale together, clv = history + 12-month prediction, and
-- more repeat orders in the same time never lower the expected rate.
select customer_id from {{ ref('fct_customer_clv') }}
where abs(predicted_orders_12m - predicted_orders_90d * 365 / 90) > 0.0001
   or abs(predicted_revenue_12m_usd - predicted_orders_12m * expected_aov_usd) > 0.01
   or abs(clv_12m_usd - (historical_net_revenue_usd + predicted_revenue_12m_usd)) > 0.01
   or days_observed < 1
   or repeat_orders != orders - 1
union all
select a.customer_id
from {{ ref('fct_customer_clv') }} as a
join {{ ref('fct_customer_clv') }} as b
  on a.days_observed = b.days_observed and a.repeat_orders > b.repeat_orders
where a.expected_repeat_rate_per_day <= b.expected_repeat_rate_per_day
