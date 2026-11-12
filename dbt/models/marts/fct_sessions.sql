-- One row per GA4 session, with its marketing channel, purchases and (where known) the customer.
-- This is the base table for attribution: sessions are the touchpoints.

with sessions as (

    select * from {{ ref('int_ga4__sessions') }}

),

channelled as (

    select
        *,
        {{ channel_group('source', 'medium') }} as channel_group
    from sessions

),

purchases as (

    select
        session_key,
        count(*) as valid_purchases,
        sum(revenue_usd) as revenue_usd
    from {{ ref('stg_ga4__purchases') }}
    group by session_key

),

links as (

    select user_pseudo_id, customer_id, link_rule, confidence
    from {{ ref('stg_identity__links') }}

)

select
    s.session_key,
    s.user_pseudo_id,
    s.ga_session_id,
    s.ga_session_number,
    s.ga_session_number = 1 as is_first_session,
    s.session_date,
    s.session_start_ts,
    s.session_end_ts,
    timestamp_diff(s.session_end_ts, s.session_start_ts, second) as duration_seconds,
    s.events,
    s.page_views,
    s.is_engaged,
    s.engagement_time_msec,
    s.landing_page,
    s.referrer,
    s.source,
    s.medium,
    s.campaign,
    s.channel_group,
    s.channel_group in ('Paid Search', 'Display', 'Paid Social', 'Affiliate', 'Email') as is_paid,
    -- Same key as stg_ad_spend.campaign_key; only paid sessions have one.
    case
        when s.channel_group in ('Paid Search', 'Display', 'Paid Social', 'Affiliate', 'Email')
        then concat(
            s.channel_group, '|',
            coalesce(nullif(trim(s.source), ''), '(not set)'), '|',
            coalesce(nullif(trim(s.medium), ''), '(not set)'), '|',
            coalesce(nullif(trim(s.campaign), ''), '(not set)'))
    end as ad_campaign_key,
    s.has_gclid,
    s.first_touch_source,
    s.first_touch_medium,
    s.first_touch_campaign,
    s.country,
    s.device_category,
    s.viewed_item,
    s.added_to_cart,
    s.began_checkout,
    s.purchase_events,
    coalesce(p.valid_purchases, 0) as valid_purchases,
    coalesce(p.revenue_usd, 0) as revenue_usd,
    coalesce(p.valid_purchases, 0) > 0 as is_converted,
    l.customer_id,
    l.customer_id is not null as is_identified,
    l.link_rule as identity_link_rule,
    l.confidence as identity_confidence
from channelled as s
left join purchases as p on p.session_key = s.session_key
left join links as l on l.user_pseudo_id = s.user_pseudo_id
