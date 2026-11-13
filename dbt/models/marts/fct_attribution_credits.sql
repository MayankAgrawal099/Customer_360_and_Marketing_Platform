-- Who gets the credit for each order: one row per (order, model, credited touchpoint).
-- Models: first_touch, last_touch, linear, time_decay. Every model shares exactly 1 unit of credit per order,
-- so every model can be summed and compared the same way. Rules in docs/attribution.md.
--
-- Which touchpoints can be credited
--   Touchpoints with a known source (has_source: not Direct, Self Referral, Unassigned or Other) when the journey
--   has any. If it has none, all of its touchpoints are used and the credit is labelled 'Direct / Unknown'.
--   If there is no touchpoint at all, the credit goes to 'No Touchpoint' with no session.
--
-- The four models
--   first_touch  100% to the earliest of those touchpoints
--   last_touch   100% to the latest of them
--   linear       an equal share (1 / n) to each of the n touchpoints
--   time_decay   each touchpoint's weight halves for every half_life_days (7) it lies before the order:
--                weight = 0.5 ^ (days_before_order / half_life_days); credit = weight / sum of the weights
-- Orders are never dropped: every order has credit totalling 1 under every model, and credited revenue adds up
-- to net revenue.

with params as (

    select 7.0 as half_life_days

),

orders as (

    select order_id, customer_id, order_ts, order_date, order_channel, ga4_match_status, is_refunded,
           order_value_usd, net_revenue_usd
    from {{ ref('fct_orders') }}

),

touchpoints as (

    select
        *,
        max(if(has_source, 1, 0)) over (partition by order_id) as order_has_source
    from {{ ref('int_conversion_touchpoints') }}

),

ranked as (

    select
        *,
        -- Touchpoints with a known source sort ahead of the rest, then by time.
        row_number() over (partition by order_id order by has_source desc, session_start_ts asc, session_key asc) as first_pick,
        row_number() over (partition by order_id order by has_source desc, session_start_ts desc, session_key desc) as last_pick
    from touchpoints

),

pool as (

    -- The touchpoints that share the credit under linear and time_decay.
    select
        t.*,
        count(*) over (partition by t.order_id) as pool_size,
        pow(0.5, t.days_before_order / p.half_life_days) as decay_weight
    from touchpoints as t
    cross join params as p
    where t.has_source or t.order_has_source = 0

),

chosen as (

    select order_id, 'first_touch' as model, session_key, session_start_ts, channel_group, source, medium, campaign,
           ad_campaign_key, is_paid, has_source, days_before_order, 1.0 as credit
    from ranked where first_pick = 1

    union all

    select order_id, 'last_touch', session_key, session_start_ts, channel_group, source, medium, campaign,
           ad_campaign_key, is_paid, has_source, days_before_order, 1.0
    from ranked where last_pick = 1

    union all

    select order_id, 'linear', session_key, session_start_ts, channel_group, source, medium, campaign,
           ad_campaign_key, is_paid, has_source, days_before_order, 1.0 / pool_size
    from pool

    union all

    select order_id, 'time_decay', session_key, session_start_ts, channel_group, source, medium, campaign,
           ad_campaign_key, is_paid, has_source, days_before_order,
           decay_weight / sum(decay_weight) over (partition by order_id)
    from pool

),

models as (

    select 'first_touch' as model
    union all
    select 'last_touch'
    union all
    select 'linear'
    union all
    select 'time_decay'

)

select
    o.order_id as conversion_id,
    m.model,
    o.customer_id,
    o.order_ts,
    o.order_date,
    o.order_channel,
    o.ga4_match_status,
    o.is_refunded,
    ch.session_key as touchpoint_session_key,
    ch.session_start_ts as touchpoint_ts,
    ch.days_before_order as touchpoint_days_before_order,
    case
        when ch.session_key is null then 'No Touchpoint'
        when ch.has_source then ch.channel_group
        else 'Direct / Unknown'
    end as credited_channel,
    case
        when ch.session_key is null then 'no_touchpoint'
        when ch.has_source then 'known_source'
        else 'direct_or_unknown'
    end as attribution_basis,
    ch.channel_group as touchpoint_channel_group,
    ch.source as touchpoint_source,
    ch.medium as touchpoint_medium,
    ch.campaign as touchpoint_campaign,
    ch.ad_campaign_key,
    coalesce(ch.is_paid, false) as is_paid,
    coalesce(ch.credit, 1.0) as credit,
    o.order_value_usd,
    o.net_revenue_usd as revenue_usd,
    coalesce(ch.credit, 1.0) * o.net_revenue_usd as credited_revenue_usd
from orders as o
cross join models as m
left join chosen as ch on ch.order_id = o.order_id and ch.model = m.model
