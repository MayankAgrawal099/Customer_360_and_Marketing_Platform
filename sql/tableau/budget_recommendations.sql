-- Tableau extract: a budget recommendation for every paid channel and every paid campaign, one row each (level = 'Channel' or
-- 'Campaign'). Rules, in order (the thresholds sit in the `rules` CTE):
--   Not enough data  fewer than min_orders attributed orders on average across the four attribution models
--   Hold             Email: its cost per click is assumed, so its ROAS is an artifact and not evidence
--   Increase         ROAS is at least increase_roas under EVERY basis (the four models and ga4_session): a cushion for product
--                    costs, which are not in the data
--   Reduce           ROAS is below reduce_roas under EVERY basis: no view says it pays back
--   Hold             otherwise: the bases disagree, or the return is modest
-- suggested_change_pct is a rule of thumb for a test, not a forecast. Spend is synthetic, so the dollar amounts are too.
with rules as (

    select 5 as min_orders, 1.5 as increase_roas, 1.0 as reduce_roas, 0.20 as increase_pct, -0.30 as reduce_pct

),

campaigns as (

    select
        'Campaign' as level,
        channel,
        campaign_key as item,
        any_value(spend_usd) as spend_usd,
        min(roas) as roas_low,
        max(roas) as roas_high,
        avg(if(model != 'ga4_session', roas, null)) as roas_models_avg,
        avg(if(model != 'ga4_session', attributed_orders, null)) as orders_models_avg,
        avg(if(model != 'ga4_session', attributed_revenue_usd, null)) as revenue_models_avg
    from `da02-customer360.marts.fct_campaign_roi`
    group by channel, campaign_key

),

channels as (

    select
        'Channel' as level,
        channel,
        channel as item,
        any_value(spend_usd) as spend_usd,
        min(roas) as roas_low,
        max(roas) as roas_high,
        avg(if(model != 'ga4_session', roas, null)) as roas_models_avg,
        avg(if(model != 'ga4_session', attributed_orders, null)) as orders_models_avg,
        avg(if(model != 'ga4_session', attributed_revenue_usd, null)) as revenue_models_avg
    from `da02-customer360.marts.fct_channel_roi`
    group by channel

),

stacked as (

    select * from channels
    union all
    select * from campaigns

),

decided as (

    select
        s.*,
        case
            when s.orders_models_avg < r.min_orders then 'Not enough data'
            when s.channel = 'Email' then 'Hold'
            when s.roas_low >= r.increase_roas then 'Increase'
            when s.roas_high < r.reduce_roas then 'Reduce'
            else 'Hold'
        end as recommendation,
        case
            when s.orders_models_avg < r.min_orders then 'Fewer than 5 attributed orders on average'
            when s.channel = 'Email' then 'Cost per email click is assumed, so ROAS is not evidence'
            when s.roas_low >= r.increase_roas then 'ROAS of 1.5 or more under every view'
            when s.roas_high < r.reduce_roas then 'ROAS below 1 under every view'
            else 'The views disagree, or the return is modest'
        end as reason,
        r.increase_pct,
        r.reduce_pct
    from stacked as s
    cross join rules as r

)

select
    level,
    channel,
    item,
    spend_usd,
    safe_divide(spend_usd, sum(spend_usd) over (partition by level)) as spend_share,
    orders_models_avg,
    revenue_models_avg,
    roas_low,
    roas_models_avg,
    roas_high,
    recommendation,
    case recommendation when 'Increase' then 1 when 'Hold' then 2 when 'Reduce' then 3 else 4 end as recommendation_order,
    reason,
    case recommendation when 'Increase' then increase_pct when 'Reduce' then reduce_pct else 0 end as suggested_change_pct,
    spend_usd * (1 + case recommendation when 'Increase' then increase_pct when 'Reduce' then reduce_pct else 0 end)
        as proposed_spend_usd
from decided
