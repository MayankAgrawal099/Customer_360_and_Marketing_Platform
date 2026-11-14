-- The same return measures rolled up to the paid channel: one row per (model, channel). Built only from fct_campaign_roi,
-- so the two tables cannot disagree. Definitions and the ga4_session benchmark are explained in fct_campaign_roi.sql
-- and docs/campaign_roi.md.

select
    model,
    channel,
    count(*) as campaigns,
    sum(days_with_spend) as campaign_days,
    sum(impressions) as impressions,
    sum(clicks) as clicks,
    sum(spend_usd) as spend_usd,
    safe_divide(sum(spend_usd), sum(clicks)) as cost_per_click,
    sum(attributed_orders) as attributed_orders,
    sum(attributed_revenue_usd) as attributed_revenue_usd,
    sum(attributed_revenue_usd) - sum(spend_usd) as profit_usd,
    safe_divide(sum(attributed_revenue_usd), sum(spend_usd)) as roas,
    safe_divide(sum(attributed_revenue_usd) - sum(spend_usd), sum(spend_usd)) as roi,
    safe_divide(sum(spend_usd), nullif(sum(attributed_orders), 0)) as cpa_usd,
    safe_divide(sum(attributed_revenue_usd), sum(clicks)) as revenue_per_click
from {{ ref('fct_campaign_roi') }}
group by model, channel
