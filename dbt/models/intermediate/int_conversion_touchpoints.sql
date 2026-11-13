-- The journey behind every conversion: one row per (CRM order, GA4 session that could have led to it).
-- This is the base for every attribution model; the models differ only in how they share credit among these rows.
--
-- Conversion  a CRM order (all 5,120, web and app). Revenue is net revenue (order value minus refunds).
-- Touchpoint  a GA4 session that
--               - belongs to the device that made the purchase (matched web orders), or to any device that identity
--                 resolution linked to the order's customer (so app orders and orders without a GA4 transaction id
--                 are attributed through the customer's website visits), and
--               - started no later than the order and no more than 30 days before it. The purchasing session itself
--                 is always kept.
--
-- has_source marks the touchpoints that tell us where the visitor came from. Four channels do not:
--   Self Referral  the visitor was on the store's own site and navigated back to it: internal, not a source
--   Direct         typed the address or no referrer
--   Unassigned     GA4 gave the session no source at all
--   Other          in this dataset only the values GA4 hides in its public sample, '<Other>' and '(data deleted)':
--                  the real source exists but is not shown to us, so there is nothing to credit
-- Attribution skips these whenever a touchpoint with a source exists (the GA4 default "last non-direct" idea).
-- Orders with no touchpoint at all (customer has no linked device, or no visit in the 30 days) stay in the
-- table's parent, fct_orders, and appear in the credits as 'No Touchpoint'.

with orders as (

    select order_id, customer_id, order_ts, ga_user_pseudo_id, ga_session_key
    from {{ ref('fct_orders') }}

),

devices as (

    select order_id, ga_user_pseudo_id as user_pseudo_id
    from orders
    where ga_user_pseudo_id is not null

    union distinct

    select o.order_id, l.user_pseudo_id
    from orders as o
    inner join {{ ref('stg_identity__links') }} as l on l.customer_id = o.customer_id

),

sessions as (

    select
        session_key,
        user_pseudo_id,
        session_date,
        session_start_ts,
        channel_group,
        source,
        medium,
        campaign,
        ad_campaign_key,
        is_paid
    from {{ ref('fct_sessions') }}

)

select
    o.order_id,
    s.session_key,
    s.user_pseudo_id,
    s.session_date,
    s.session_start_ts,
    s.channel_group,
    s.source,
    s.medium,
    s.campaign,
    s.ad_campaign_key,
    s.is_paid,
    s.channel_group not in ('Self Referral', 'Direct', 'Unassigned', 'Other') as has_source,
    -- App orders and orders without a transaction id have no purchasing session: false, never null.
    coalesce(s.session_key = o.ga_session_key, false) as is_purchase_session,
    timestamp_diff(o.order_ts, s.session_start_ts, second) / 86400.0 as days_before_order
from orders as o
inner join devices as d on d.order_id = o.order_id
inner join sessions as s on s.user_pseudo_id = d.user_pseudo_id
where s.session_key = o.ga_session_key
   or (s.session_start_ts <= o.order_ts and s.session_start_ts >= timestamp_sub(o.order_ts, interval 30 day))
