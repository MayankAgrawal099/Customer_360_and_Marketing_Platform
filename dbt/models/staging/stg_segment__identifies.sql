-- One row per Segment identify event: device (anonymousId) linked to a customer (userId).

select
    messageId as message_id,
    `timestamp` as event_ts,
    anonymousId as user_pseudo_id,
    userId as customer_id,
    traits.email as email,
    traits.emailSha256 as email_sha256,
    traits.firstName as first_name,
    traits.lastName as last_name,
    traits.country as country,
    traits.createdAt as customer_created_at
from {{ source('raw', 'segment_identifies') }}
