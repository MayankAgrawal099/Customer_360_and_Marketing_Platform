select channel, model, spend_usd, attributed_orders, attributed_revenue_usd, roas, roi, cpa_usd
from `da02-customer360.marts.fct_channel_roi`
order by channel, model;

select campaign_key, model, spend_usd, attributed_orders, attributed_revenue_usd, roas, cpa_usd
from `da02-customer360.marts.fct_campaign_roi`
where model in ('last_touch','ga4_session')
order by spend_usd desc, campaign_key, model
limit 30;