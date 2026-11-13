-- One row per CRM order describing its journey, to show where the models can differ at all:
-- an order with a single known-source touchpoint gets the same credit under first and last touch.

with orders as (

    select order_id, customer_id, order_ts, order_channel, ga4_match_status, net_revenue_usd
    from {{ ref('fct_orders') }}

),

journeys as (

    select
        order_id,
        count(*) as touchpoints,
        countif(has_source) as source_touchpoints,
        count(distinct if(has_source, channel_group, null)) as distinct_source_channels,
        min(session_start_ts) as first_touchpoint_ts,
        max(session_start_ts) as last_touchpoint_ts
    from {{ ref('int_conversion_touchpoints') }}
    group by order_id

),

picked as (

    select
        conversion_id as order_id,
        max(if(model = 'first_touch', credited_channel, null)) as first_touch_channel,
        max(if(model = 'last_touch', credited_channel, null)) as last_touch_channel
    from {{ ref('fct_attribution_credits') }}
    group by conversion_id

)

select
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_channel,
    o.ga4_match_status,
    o.net_revenue_usd,
    coalesce(j.touchpoints, 0) as touchpoints,
    coalesce(j.source_touchpoints, 0) as source_touchpoints,
    coalesce(j.distinct_source_channels, 0) as distinct_source_channels,
    timestamp_diff(o.order_ts, j.first_touchpoint_ts, second) / 86400.0 as days_from_first_touchpoint,
    p.first_touch_channel,
    p.last_touch_channel,
    p.first_touch_channel != p.last_touch_channel as first_and_last_differ
from orders as o
left join journeys as j on j.order_id = o.order_id
left join picked as p on p.order_id = o.order_id
