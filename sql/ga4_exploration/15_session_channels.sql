-- title: Session-level source, medium and campaign (first value seen in each session)
-- max_rows: 40
WITH ev AS (
  SELECT
    user_pseudo_id,
    event_timestamp,
    event_name,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS sid,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'source') AS src,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium') AS med,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'campaign') AS camp,
    EXISTS (SELECT 1 FROM UNNEST(event_params) WHERE key = 'gclid') AS has_gclid
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
),
sessions AS (
  SELECT
    user_pseudo_id,
    sid,
    ARRAY_AGG(src IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS source,
    ARRAY_AGG(med IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS medium,
    ARRAY_AGG(camp IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS campaign,
    LOGICAL_OR(has_gclid) AS has_gclid,
    LOGICAL_OR(event_name = 'purchase') AS has_purchase
  FROM ev
  GROUP BY user_pseudo_id, sid
)
SELECT source, medium, campaign, has_gclid, COUNT(*) AS sessions, COUNTIF(has_purchase) AS purchase_sessions
FROM sessions
GROUP BY source, medium, campaign, has_gclid
ORDER BY sessions DESC
LIMIT 40
