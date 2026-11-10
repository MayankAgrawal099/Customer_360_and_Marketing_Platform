-- title: Sessions (a session = user_pseudo_id + ga_session_id)
-- max_rows: 5
WITH e AS (
  SELECT
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
)
SELECT
  COUNT(*) AS events,
  COUNT(DISTINCT user_pseudo_id) AS users,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING))) AS sessions,
  COUNTIF(ga_session_id IS NULL) AS events_without_session_id,
  ROUND(SAFE_DIVIDE(COUNT(*), COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING)))), 2) AS events_per_session
FROM e
