-- Basic sanity of every session row. Returns the sessions that break a rule.
select session_key
from {{ ref('fct_sessions') }}
where session_end_ts < session_start_ts
   or duration_seconds < 0
   or events < 1
   or page_views > events
   or (valid_purchases > 0 and purchase_events = 0)
   or (is_converted != (valid_purchases > 0))
   or (is_paid != (ad_campaign_key is not null))
   or (is_identified and customer_id is null)
