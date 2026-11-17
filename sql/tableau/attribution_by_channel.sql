-- Tableau extract: what each attribution model credits to each channel, one row per (model, credited channel).
-- fct_attribution_by_channel (orders, revenue and shares per model) plus the channel's role and how far the models disagree.
select
    c.model,
    case c.model
        when 'first_touch' then 'First touch'
        when 'last_touch' then 'Last touch'
        when 'linear' then 'Linear'
        when 'time_decay' then 'Time decay'
    end as model_label,
    case c.model
        when 'first_touch' then 1
        when 'last_touch' then 2
        when 'linear' then 3
        when 'time_decay' then 4
    end as model_order,
    c.credited_channel,
    m.is_known_source,
    m.is_paid_channel,
    m.role,
    c.attributed_orders,
    c.attributed_revenue_usd,
    c.share_of_orders,
    c.share_of_revenue,
    m.revenue_spread_usd,
    m.revenue_spread_pct,
    m.introducing_gap_usd
from `da02-customer360.marts.fct_attribution_by_channel` as c
left join `da02-customer360.marts.fct_attribution_model_comparison` as m on m.credited_channel = c.credited_channel
