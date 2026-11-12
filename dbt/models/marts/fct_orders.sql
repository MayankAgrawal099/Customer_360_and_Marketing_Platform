-- One row per CRM order, with the customer's order history and, for web orders, the GA4 session that
-- produced it (and so the channel that session came from).
--
-- ga4_match_status says how far the link to GA4 goes:
--   matched               web order whose GA4 transaction id was found among the valid GA4 purchases
--   web_no_transaction_id web order that carries no transaction id (about 8%): no GA4 session can be named
--   app_order             app order: GA4 only sees the website, so it never appears there
--   web_unmatched         transaction id present but not found in GA4 (a test makes sure this stays at zero)

with orders as (

    select * from {{ ref('stg_crm__orders') }}

),

customers as (

    select
        customer_id,
        country as customer_country,
        created_at as customer_created_at
    from {{ ref('stg_crm__customers') }}

),

purchases as (

    select transaction_id, user_pseudo_id, session_key, revenue_usd
    from {{ ref('stg_ga4__purchases') }}

),

sessions as (

    select
        session_key,
        ga_session_number,
        session_date,
        channel_group,
        source,
        medium,
        campaign
    from {{ ref('fct_sessions') }}

),

sequenced as (

    select
        *,
        row_number() over (partition by customer_id order by order_ts, order_id) as order_number,
        lag(order_ts) over (partition by customer_id order by order_ts, order_id) as previous_order_ts,
        min(order_ts) over (partition by customer_id) as first_order_ts
    from orders

)

select
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_date,
    o.order_channel,
    o.status,
    o.is_refunded,
    o.order_value_usd,
    o.refund_usd,
    o.net_revenue_usd,
    o.item_count,
    o.order_number,
    o.order_number = 1 as is_first_order,
    o.previous_order_ts,
    date_diff(o.order_date, date(o.previous_order_ts), day) as days_since_previous_order,
    date_diff(o.order_date, date(o.first_order_ts), day) as days_since_first_order,
    c.customer_country,
    c.customer_created_at,
    o.ga_transaction_id,
    case
        when o.order_channel = 'app' then 'app_order'
        when o.ga_transaction_id is null then 'web_no_transaction_id'
        when p.transaction_id is not null then 'matched'
        else 'web_unmatched'
    end as ga4_match_status,
    p.user_pseudo_id as ga_user_pseudo_id,
    p.session_key as ga_session_key,
    p.revenue_usd as ga_revenue_usd,
    s.ga_session_number as purchase_session_number,
    s.session_date as purchase_session_date,
    s.channel_group as purchase_channel_group,
    s.source as purchase_source,
    s.medium as purchase_medium,
    s.campaign as purchase_campaign
from sequenced as o
left join customers as c on c.customer_id = o.customer_id
left join purchases as p on p.transaction_id = o.ga_transaction_id
left join sessions as s on s.session_key = p.session_key
