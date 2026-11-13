select count(*) as buyers,
       round(avg(historical_net_revenue_usd), 2) as avg_historical,
       round(avg(predicted_revenue_90d_usd), 2) as avg_pred_90d,
       round(avg(predicted_revenue_12m_usd), 2) as avg_pred_12m,
       round(avg(clv_12m_usd), 2) as avg_clv_12m,
       round(max(clv_12m_usd), 2) as max_clv_12m,
       round(max(population_repeat_rate_per_day), 5) as pop_rate_per_day,
       round(max(population_aov_usd), 2) as pop_aov
from `da02-customer360.marts.fct_customer_clv`;