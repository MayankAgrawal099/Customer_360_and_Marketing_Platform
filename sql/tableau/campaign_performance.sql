-- Tableau extract: return and cost for each paid campaign, one row per (model, campaign). fct_campaign_roi joined to
-- fct_campaign_cpa. Five bases: the four attribution models plus ga4_session (the narrowest view).
select
    r.model,
    case r.model
        when 'first_touch' then 'First touch'
        when 'last_touch' then 'Last touch'
        when 'linear' then 'Linear'
        when 'time_decay' then 'Time decay'
        when 'ga4_session' then 'GA4 session'
    end as model_label,
    case r.model
        when 'first_touch' then 1
        when 'last_touch' then 2
        when 'linear' then 3
        when 'time_decay' then 4
        when 'ga4_session' then 5
    end as model_order,
    r.campaign_key,
    r.channel,
    r.source,
    r.medium,
    r.campaign,
    r.first_spend_date,
    r.last_spend_date,
    r.days_with_spend,
    r.impressions,
    r.clicks,
    r.spend_usd,
    r.cost_per_click,
    r.attributed_orders,
    c.new_customers,
    c.repeat_orders,
    r.attributed_revenue_usd,
    r.profit_usd,
    r.roas,
    r.roi,
    r.cpa_usd,
    c.cac_usd,
    c.avg_order_value_usd,
    c.cpa_to_aov,
    c.has_enough_orders,
    c.cpa_rank,
    c.cpa_vs_channel,
    r.revenue_per_click
from `da02-customer360.marts.fct_campaign_roi` as r
inner join `da02-customer360.marts.fct_campaign_cpa` as c on c.model = r.model and c.campaign_key = r.campaign_key
