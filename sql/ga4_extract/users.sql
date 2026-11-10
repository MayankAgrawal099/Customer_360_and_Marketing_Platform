-- file: users.csv
-- One row per GA4 user (user_pseudo_id): when first and last seen, size of activity, and first known attributes.
WITH e AS (
  SELECT
    user_pseudo_id,
    event_timestamp,
    event_name,
    geo.country AS country,
    device.category AS device_category,
    traffic_source.source AS source,
    traffic_source.medium AS medium,
    traffic_source.name AS campaign,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE user_pseudo_id IS NOT NULL
)
SELECT
  user_pseudo_id,
  TIMESTAMP_MICROS(MIN(event_timestamp)) AS first_seen_ts,
  TIMESTAMP_MICROS(MAX(event_timestamp)) AS last_seen_ts,
  COUNT(DISTINCT ga_session_id) AS sessions,
  COUNTIF(event_name = 'purchase') AS purchase_events,
  ARRAY_AGG(country IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS country,
  ARRAY_AGG(device_category IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS device_category,
  ARRAY_AGG(source IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS source,
  ARRAY_AGG(medium IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS medium,
  ARRAY_AGG(campaign IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS campaign
FROM e
GROUP BY user_pseudo_id
