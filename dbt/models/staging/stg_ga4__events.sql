{{
  config(
    materialized='table',
    cluster_by=['event_name', 'user_pseudo_id']
  )
}}

-- A table, not a view: reading event_params scans about 1.3 GB, and every model downstream starts here.
-- Not partitioned: BigQuery sandbox partitions older than 60 days would be deleted straight away.

with params as (

    select
        parse_date('%Y%m%d', event_date) as event_date,
        timestamp_micros(event_timestamp) as event_ts,
        event_name,
        user_pseudo_id,
        (select value.int_value from unnest(event_params) where key = 'ga_session_id') as ga_session_id,
        (select value.int_value from unnest(event_params) where key = 'ga_session_number') as ga_session_number,
        (select value.string_value from unnest(event_params) where key = 'page_location') as page_location,
        (select value.string_value from unnest(event_params) where key = 'page_referrer') as page_referrer,
        (select value.string_value from unnest(event_params) where key = 'source') as session_source,
        (select value.string_value from unnest(event_params) where key = 'medium') as session_medium,
        (select value.string_value from unnest(event_params) where key = 'campaign') as session_campaign,
        (select value.string_value from unnest(event_params) where key = 'term') as session_term,
        exists (select 1 from unnest(event_params) where key = 'gclid') as has_gclid,
        (select value.int_value from unnest(event_params) where key = 'engagement_time_msec') as engagement_time_msec,
        (select coalesce(value.string_value, cast(value.int_value as string)) from unnest(event_params) where key = 'session_engaged') = '1' as is_engaged_session,
        ecommerce.transaction_id as transaction_id,
        ecommerce.purchase_revenue_in_usd as purchase_revenue_usd,
        ecommerce.total_item_quantity as item_quantity,
        geo.country as country,
        device.category as device_category,
        device.operating_system as operating_system,
        device.web_info.browser as browser,
        platform,
        traffic_source.source as first_touch_source,
        traffic_source.medium as first_touch_medium,
        traffic_source.name as first_touch_campaign,
        timestamp_micros(user_first_touch_timestamp) as user_first_touch_ts
    from {{ source('raw', 'ga4_events') }}

)

select
    *,
    -- A session is a device plus its ga_session_id.
    concat(user_pseudo_id, '.', cast(ga_session_id as string)) as session_key
from params
