-- One row per CRM customer (all of them, including sign-ups who never ordered): who they are, what
-- they bought, and what is known about their website visits.
--
-- Three sources are summarised separately (one row per customer each) and then joined, so no join can
-- double a customer or their revenue:
--   orders    from fct_orders (CRM orders, all channels)
--   devices   from stg_identity__links (GA4 devices the identity rules linked to the customer)
--   sessions  from fct_sessions (sessions on those linked devices only: about 4% of all sessions)
-- Recency is not calculated here: it needs an as-of date, which the RFM model fixes.

with customers as (

    select * from {{ ref('stg_crm__customers') }}

),

orders as (

    select
        customer_id,
        count(*) as orders,
        countif(is_refunded) as refunded_orders,
        countif(order_channel = 'web') as web_orders,
        countif(order_channel = 'app') as app_orders,
        sum(item_count) as items,
        sum(order_value_usd) as gross_revenue_usd,
        sum(refund_usd) as refund_usd,
        sum(net_revenue_usd) as net_revenue_usd,
        min(order_ts) as first_order_ts,
        max(order_ts) as last_order_ts,
        min(order_date) as first_order_date,
        max(order_date) as last_order_date
    from {{ ref('fct_orders') }}
    group by customer_id

),

first_orders as (

    select
        customer_id,
        order_channel as first_order_channel,
        ga4_match_status as first_order_ga4_match_status,
        purchase_channel_group as first_order_channel_group
    from {{ ref('fct_orders') }}
    where is_first_order

),

devices as (

    select
        customer_id,
        count(*) as linked_devices,
        max(confidence = 'high') as has_high_confidence_link
    from {{ ref('stg_identity__links') }}
    group by customer_id

),

ranked_sessions as (

    select
        customer_id,
        session_date,
        session_start_ts,
        channel_group,
        source,
        medium,
        is_converted,
        row_number() over (partition by customer_id order by session_start_ts, session_key) as session_rank
    from {{ ref('fct_sessions') }}
    where customer_id is not null

),

sessions as (

    select
        customer_id,
        count(*) as sessions,
        countif(is_converted) as converted_sessions,
        min(session_date) as first_session_date,
        max(session_date) as last_session_date,
        max(if(session_rank = 1, channel_group, null)) as first_session_channel_group,
        max(if(session_rank = 1, source, null)) as first_session_source,
        max(if(session_rank = 1, medium, null)) as first_session_medium
    from ranked_sessions
    group by customer_id

)

select
    c.customer_id,
    c.full_name,
    c.email,
    c.email_sha256,
    c.country,
    c.created_at,
    c.created_date,
    date_trunc(c.created_date, month) as created_month,
    c.marketing_opt_in,

    coalesce(o.orders, 0) as orders,
    coalesce(o.orders, 0) > 0 as is_buyer,
    coalesce(o.orders, 0) > 1 as is_repeat_buyer,
    coalesce(o.refunded_orders, 0) as refunded_orders,
    coalesce(o.web_orders, 0) as web_orders,
    coalesce(o.app_orders, 0) as app_orders,
    coalesce(o.items, 0) as items,
    coalesce(o.gross_revenue_usd, 0) as gross_revenue_usd,
    coalesce(o.refund_usd, 0) as refund_usd,
    coalesce(o.net_revenue_usd, 0) as net_revenue_usd,
    safe_divide(o.gross_revenue_usd, o.orders) as avg_order_value_usd,
    o.first_order_ts,
    o.last_order_ts,
    o.first_order_date,
    o.last_order_date,
    f.first_order_channel,
    f.first_order_ga4_match_status,
    f.first_order_channel_group,

    coalesce(d.linked_devices, 0) as linked_devices,
    coalesce(d.linked_devices, 0) > 0 as has_linked_device,
    coalesce(d.has_high_confidence_link, false) as has_high_confidence_link,

    coalesce(s.sessions, 0) as sessions,
    coalesce(s.converted_sessions, 0) as converted_sessions,
    s.first_session_date,
    s.last_session_date,
    s.first_session_channel_group,
    s.first_session_source,
    s.first_session_medium
from customers as c
left join orders as o on o.customer_id = c.customer_id
left join first_orders as f on f.customer_id = c.customer_id
left join devices as d on d.customer_id = c.customer_id
left join sessions as s on s.customer_id = c.customer_id
