-- Return on ad spend for every paid campaign: one row per (model, campaign). Spend comes from stg_ad_spend, revenue from
-- the attribution models, so the same campaign can be compared under first touch, last touch, linear and time decay.
--
-- model          first_touch, last_touch, linear, time_decay: net revenue of CRM orders credited to the campaign's
--                sessions (fct_attribution_credits), plus
--                ga4_session: every GA4 purchase credited to the campaign of its own session (fct_sessions). It needs
--                neither the CRM nor identity resolution, so it covers the same visitors as the ad spend does and is
--                the narrowest view. It uses GA4 purchase revenue, which has no refunds.
-- Why two bases: ga4_session counts a purchase only for the campaign of the session in which it happened. The four
-- models look back over the customer's journey (30 days, linked devices), so they also credit campaigns that came
-- earlier in it. Read ga4_session next to them as the narrowest view: the gap is the value of assists and of
-- cross-device journeys. The CRM covers only about 81% of GA4 purchases, which works the other way.
--
-- roas            revenue / spend (return on ad spend: $ of revenue per $ of spend)
-- roi             (revenue - spend) / spend
-- cpa_usd         spend / attributed orders: cost to win one order (empty when the campaign got no orders)
-- profit_usd      revenue - spend (revenue, not margin: product costs are not in the data)
-- Spend is synthetic (assumed cost per click, see docs/synthetic_data.md): the method is real, the amounts are not.

with spend as (

    select
        campaign_key,
        channel,
        source,
        medium,
        campaign,
        min(date) as first_spend_date,
        max(date) as last_spend_date,
        count(distinct date) as days_with_spend,
        sum(impressions) as impressions,
        sum(clicks) as clicks,
        sum(spend_usd) as spend_usd
    from {{ ref('stg_ad_spend') }}
    group by campaign_key, channel, source, medium, campaign

),

models as (

    select 'first_touch' as model
    union all
    select 'last_touch'
    union all
    select 'linear'
    union all
    select 'time_decay'
    union all
    select 'ga4_session'

),

revenue as (

    select
        model,
        ad_campaign_key as campaign_key,
        sum(credit) as attributed_orders,
        sum(credited_revenue_usd) as attributed_revenue_usd
    from {{ ref('fct_attribution_credits') }}
    where ad_campaign_key is not null
    group by model, ad_campaign_key

    union all

    select
        'ga4_session',
        ad_campaign_key,
        sum(valid_purchases),
        sum(revenue_usd)
    from {{ ref('fct_sessions') }}
    where is_paid
    group by ad_campaign_key

),

joined as (

    select
        m.model,
        s.*,
        coalesce(r.attributed_orders, 0) as attributed_orders,
        coalesce(r.attributed_revenue_usd, 0) as attributed_revenue_usd
    from spend as s
    cross join models as m
    left join revenue as r on r.campaign_key = s.campaign_key and r.model = m.model

)

select
    model,
    campaign_key,
    channel,
    source,
    medium,
    campaign,
    first_spend_date,
    last_spend_date,
    days_with_spend,
    impressions,
    clicks,
    spend_usd,
    safe_divide(spend_usd, clicks) as cost_per_click,
    attributed_orders,
    attributed_revenue_usd,
    attributed_revenue_usd - spend_usd as profit_usd,
    safe_divide(attributed_revenue_usd, spend_usd) as roas,
    safe_divide(attributed_revenue_usd - spend_usd, spend_usd) as roi,
    safe_divide(spend_usd, nullif(attributed_orders, 0)) as cpa_usd,
    safe_divide(attributed_revenue_usd, clicks) as revenue_per_click
from joined
