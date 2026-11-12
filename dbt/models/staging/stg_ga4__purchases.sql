-- One row per valid GA4 purchase transaction.
-- Dropped: purchases whose transaction id is missing or "(not set)", purchases with no revenue, and
-- repeats of the same transaction (the earliest event is kept). Same rule as sql/ga4_extract/purchases.sql,
-- which the synthetic CRM orders were built from.

select
    transaction_id,
    user_pseudo_id,
    session_key,
    ga_session_id,
    event_ts,
    event_date,
    purchase_revenue_usd as revenue_usd,
    item_quantity,
    country,
    device_category
from {{ ref('stg_ga4__events') }}
where event_name = 'purchase'
  and transaction_id is not null
  and transaction_id != '(not set)'
  and purchase_revenue_usd > 0
qualify row_number() over (partition by transaction_id order by event_ts, user_pseudo_id) = 1
