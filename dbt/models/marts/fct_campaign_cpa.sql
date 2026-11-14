-- Cost per acquisition for every paid campaign: one row per (model, campaign). Built on fct_campaign_roi (spend, orders,
-- revenue) and adds who the orders came from.
--
-- cpa_usd              spend / attributed orders: cost to win one ORDER
-- cac_usd              spend / new customers: cost to win one NEW customer (a customer's first order). Empty under
--                      ga4_session, which has no customer, and for campaigns that won no new customer
-- new_customers        credited first orders (fractions under linear and time decay)
-- repeat_orders        attributed orders - new customers
-- avg_order_value_usd  revenue / orders
-- cpa_to_aov           cpa_usd / avg_order_value_usd: below 1 the order's own revenue covers what it cost to win
-- has_enough_orders    5 or more attributed orders. Below that a CPA moves a lot with one order, so it is not ranked
-- cpa_rank             1 = cheapest order among campaigns with enough orders in the same model (empty otherwise)
-- cpa_vs_channel       cpa_usd / the channel's CPA under the same model: below 1 beats its channel
-- Spend is synthetic (assumed cost per click), so the method is real and the dollar amounts are not.

with roi as (

    select * from {{ ref('fct_campaign_roi') }}

),

new_customers as (

    select
        c.model,
        c.ad_campaign_key as campaign_key,
        sum(c.credit) as new_customers
    from {{ ref('fct_attribution_credits') }} as c
    inner join {{ ref('fct_orders') }} as o on o.order_id = c.conversion_id
    where c.ad_campaign_key is not null and o.is_first_order
    group by c.model, c.ad_campaign_key

),

channel as (

    select
        model,
        channel,
        safe_divide(sum(spend_usd), nullif(sum(attributed_orders), 0)) as channel_cpa_usd
    from roi
    group by model, channel

),

joined as (

    select
        r.*,
        if(r.model = 'ga4_session', cast(null as float64), coalesce(n.new_customers, 0)) as new_customers,
        ch.channel_cpa_usd
    from roi as r
    left join new_customers as n on n.model = r.model and n.campaign_key = r.campaign_key
    left join channel as ch on ch.model = r.model and ch.channel = r.channel

)

select
    model,
    campaign_key,
    channel,
    source,
    medium,
    campaign,
    spend_usd,
    clicks,
    attributed_orders,
    new_customers,
    attributed_orders - new_customers as repeat_orders,
    attributed_revenue_usd,
    cpa_usd,
    safe_divide(spend_usd, nullif(new_customers, 0)) as cac_usd,
    safe_divide(attributed_revenue_usd, nullif(attributed_orders, 0)) as avg_order_value_usd,
    safe_divide(cpa_usd, safe_divide(attributed_revenue_usd, nullif(attributed_orders, 0))) as cpa_to_aov,
    attributed_orders >= 5 as has_enough_orders,
    if(attributed_orders >= 5,
       rank() over (partition by model, attributed_orders >= 5 order by cpa_usd, campaign_key), null) as cpa_rank,
    safe_divide(cpa_usd, channel_cpa_usd) as cpa_vs_channel
from joined
