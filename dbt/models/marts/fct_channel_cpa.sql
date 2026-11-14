-- Cost per acquisition for each paid channel: one row per (model, channel). Built only from fct_campaign_cpa, so the two
-- cannot disagree. Definitions are in fct_campaign_cpa.sql and docs/cpa.md.

with rolled as (

    select
        model,
        channel,
        count(*) as campaigns,
        sum(spend_usd) as spend_usd,
        sum(clicks) as clicks,
        sum(attributed_orders) as attributed_orders,
        sum(new_customers) as new_customers,
        sum(attributed_revenue_usd) as attributed_revenue_usd
    from {{ ref('fct_campaign_cpa') }}
    group by model, channel

)

select
    model,
    channel,
    campaigns,
    spend_usd,
    clicks,
    attributed_orders,
    new_customers,
    attributed_orders - new_customers as repeat_orders,
    attributed_revenue_usd,
    safe_divide(spend_usd, nullif(attributed_orders, 0)) as cpa_usd,
    safe_divide(spend_usd, nullif(new_customers, 0)) as cac_usd,
    safe_divide(attributed_revenue_usd, nullif(attributed_orders, 0)) as avg_order_value_usd,
    safe_divide(safe_divide(spend_usd, nullif(attributed_orders, 0)),
                safe_divide(attributed_revenue_usd, nullif(attributed_orders, 0))) as cpa_to_aov,
    attributed_orders >= 5 as has_enough_orders,
    if(attributed_orders >= 5,
       rank() over (partition by model, attributed_orders >= 5 order by safe_divide(spend_usd, nullif(attributed_orders, 0)), channel),
       null) as cpa_rank
from rolled
