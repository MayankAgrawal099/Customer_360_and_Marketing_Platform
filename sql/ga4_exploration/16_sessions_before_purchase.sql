-- title: How many sessions does a buyer have up to their first purchase? (capped at 6)
-- max_rows: 10
WITH ev AS (
  SELECT
    user_pseudo_id,
    event_name,
    event_timestamp,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS sid
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
),
first_purchase AS (
  SELECT user_pseudo_id, MIN(event_timestamp) AS purchase_ts
  FROM ev
  WHERE event_name = 'purchase'
  GROUP BY user_pseudo_id
),
per_buyer AS (
  SELECT e.user_pseudo_id, COUNT(DISTINCT e.sid) AS sessions_before
  FROM ev AS e
  JOIN first_purchase AS p ON e.user_pseudo_id = p.user_pseudo_id
  WHERE e.event_timestamp <= p.purchase_ts
  GROUP BY e.user_pseudo_id
)
SELECT LEAST(sessions_before, 6) AS sessions_before_purchase_capped, COUNT(*) AS buyers
FROM per_buyer
GROUP BY sessions_before_purchase_capped
ORDER BY sessions_before_purchase_capped
