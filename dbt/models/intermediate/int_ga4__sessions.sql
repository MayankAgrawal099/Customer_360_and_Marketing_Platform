-- One row per GA4 session (a device plus its ga_session_id), summarised from its events.
-- "First value" columns take the earliest non-empty value seen in the session, the same rule as
-- sql/ga4_extract/daily_traffic.sql, which sized the synthetic ad spend.

select
    session_key,
    user_pseudo_id,
    ga_session_id,
    min(ga_session_number) as ga_session_number,
    min(event_date) as session_date,
    min(event_ts) as session_start_ts,
    max(event_ts) as session_end_ts,
    count(*) as events,
    countif(event_name = 'page_view') as page_views,
    countif(event_name = 'purchase') as purchase_events,
    coalesce(logical_or(event_name = 'view_item'), false) as viewed_item,
    coalesce(logical_or(event_name = 'add_to_cart'), false) as added_to_cart,
    coalesce(logical_or(event_name = 'begin_checkout'), false) as began_checkout,
    coalesce(logical_or(is_engaged_session), false) as is_engaged,
    coalesce(sum(engagement_time_msec), 0) as engagement_time_msec,
    coalesce(logical_or(has_gclid), false) as has_gclid,
    array_agg(page_location ignore nulls order by event_ts)[safe_offset(0)] as landing_page,
    array_agg(page_referrer ignore nulls order by event_ts)[safe_offset(0)] as referrer,
    array_agg(session_source ignore nulls order by event_ts)[safe_offset(0)] as source,
    array_agg(session_medium ignore nulls order by event_ts)[safe_offset(0)] as medium,
    array_agg(session_campaign ignore nulls order by event_ts)[safe_offset(0)] as campaign,
    array_agg(country ignore nulls order by event_ts)[safe_offset(0)] as country,
    array_agg(device_category ignore nulls order by event_ts)[safe_offset(0)] as device_category,
    array_agg(first_touch_source ignore nulls order by event_ts)[safe_offset(0)] as first_touch_source,
    array_agg(first_touch_medium ignore nulls order by event_ts)[safe_offset(0)] as first_touch_medium,
    array_agg(first_touch_campaign ignore nulls order by event_ts)[safe_offset(0)] as first_touch_campaign
from {{ ref('stg_ga4__events') }}
where ga_session_id is not null
group by user_pseudo_id, ga_session_id, session_key
