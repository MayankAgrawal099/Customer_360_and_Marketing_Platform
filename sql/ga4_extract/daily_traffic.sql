-- file: daily_traffic.csv
-- Sessions per start date for each session-level (source, medium, campaign), the first value seen in the session.
-- Sessions with no source params stay NULL (treated as "Unassigned"). Used to size the synthetic ad spend.
WITH ev AS (
  SELECT
    user_pseudo_id,
    event_timestamp,
    PARSE_DATE('%Y%m%d', event_date) AS event_day,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS sid,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'source') AS src,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium') AS med,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'campaign') AS camp
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
),
sessions AS (
  SELECT
    user_pseudo_id,
    sid,
    MIN(event_day) AS date,
    ARRAY_AGG(src IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS source,
    ARRAY_AGG(med IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS medium,
    ARRAY_AGG(camp IGNORE NULLS ORDER BY event_timestamp LIMIT 1)[SAFE_OFFSET(0)] AS campaign
  FROM ev
  WHERE sid IS NOT NULL
  GROUP BY user_pseudo_id, sid
)
SELECT date, source, medium, campaign, COUNT(*) AS sessions
FROM sessions
GROUP BY date, source, medium, campaign
ORDER BY date, source, medium, campaign
