-- Orders and net revenue credited to each channel under each attribution model: one row per (model, channel).
-- Built only from fct_attribution_credits, so every model that adds rows there appears here automatically.

with credits as (

    select * from {{ ref('fct_attribution_credits') }}

),

by_channel as (

    select
        model,
        credited_channel,
        sum(credit) as attributed_orders,
        sum(credited_revenue_usd) as attributed_revenue_usd
    from credits
    group by model, credited_channel

)

select
    model,
    credited_channel,
    attributed_orders,
    attributed_revenue_usd,
    attributed_orders / sum(attributed_orders) over (partition by model) as share_of_orders,
    attributed_revenue_usd / nullif(sum(attributed_revenue_usd) over (partition by model), 0) as share_of_revenue
from by_channel
