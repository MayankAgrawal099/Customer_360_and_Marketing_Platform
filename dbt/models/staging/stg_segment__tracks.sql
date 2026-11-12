-- One row per Segment server-side track event. Carries the customer only, never a device.

select
    messageId as message_id,
    `timestamp` as event_ts,
    userId as customer_id,
    event as event_name,
    properties.order_id as order_id,
    properties.revenue as revenue_usd,
    properties.currency as currency,
    properties.channel as order_channel,
    properties.status as order_status,
    properties.email_opt_in as email_opt_in
from {{ source('raw', 'segment_tracks') }}
