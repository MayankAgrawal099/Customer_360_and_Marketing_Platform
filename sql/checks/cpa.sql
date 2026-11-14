select channel, model, spend_usd, attributed_orders, new_customers, cpa_usd, cac_usd, avg_order_value_usd, cpa_to_aov, cpa_rank
from `da02-customer360.marts.fct_channel_cpa`
order by channel, model;

select campaign_key, model, spend_usd, attributed_orders, new_customers, cpa_usd, cac_usd, cpa_to_aov, cpa_rank, cpa_vs_channel
from `da02-customer360.marts.fct_campaign_cpa`
where model in ('last_touch','linear') and has_enough_orders
order by model, cpa_rank
limit 30;