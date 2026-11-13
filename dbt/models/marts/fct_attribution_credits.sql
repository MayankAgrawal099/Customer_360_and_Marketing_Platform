-- Who gets the credit for each order, one row per (order, model, credited touchpoint).
-- Models in this table: first_touch and last_touch. Later models (linear, time_decay) add rows with credit
-- shares that sum to 1 per order and model, so every model can be summed and compared the same way.
--
-- Rules (full text in docs/attribution.md)
--   first_touch  the EARLIEST touchpoint with a known source gets 100% of the order's net revenue
--   last_touch   the LATEST touchpoint with a known source gets 100%
--   If the journey has no touchpoint with a known source (only Direct, Unassigned, Self Referral or Other sessions),
--   the credit goes to 'Direct / Unknown', on the earliest (first_touch) or latest (last_touch) of those sessions.
--   If there is no touchpoint at all, the credit goes to 'No Touchpoint' with no session.
-- Orders are never dropped: every order has exactly one row per model, and credited revenue adds up to net revenue.

with orders as (

    select order_id, customer_id, order_ts, order_date, order_channel, ga4_match_status, is_refunded,
           order_value_usd, net_revenue_usd
    from {{ ref('fct_orders') }}

),

touchpoints as (

    select * from {{ ref('int_conversion_touchpoints') }}

),

ranked as (

    select
        *,
        -- Touchpoints with a known source sort ahead of the rest, then by time.
        row_number() over (partition by order_id order by has_source desc, session_start_ts asc, session_key asc) as first_pick,
        row_number() over (partition by order_id order by has_source desc, session_start_ts desc, session_key desc) as last_pick
    from touchpoints

),

chosen as (

    select order_id, 'first_touch' as model, session_key, session_start_ts, channel_group, source, medium, campaign, ad_campaign_key, is_paid, has_source
    from ranked where first_pick = 1

    union all

    select order_id, 'last_touch' as model, session_key, session_start_ts, channel_group, source, medium, campaign, ad_campaign_key, is_paid, has_source
    from ranked where last_pick = 1

),

models as (

    select 'first_touch' as model
    union all
    select 'last_touch'

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
    1.0 as credit,
    o.order_value_usd,
    o.net_revenue_usd as revenue_usd,
    1.0 * o.net_revenue_usd as credited_revenue_usd
from orders as o
cross join models as m
left join chosen as ch on ch.order_id = o.order_id and ch.model = m.model
