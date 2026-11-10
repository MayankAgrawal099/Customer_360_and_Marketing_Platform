-- file: daily_traffic.csv
-- Sessions per day for each (source, medium, campaign), used to size the synthetic ad spend.
WITH e AS (
  SELECT
    PARSE_DATE('%Y%m%d', event_date) AS date,
    user_pseudo_id,
    traffic_source.source AS source,
    traffic_source.medium AS medium,
    traffic_source.name AS campaign,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
)
SELECT
  date, source, medium, campaign,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST(ga_session_id AS STRING))) AS sessions
FROM e
GROUP BY date, source, medium, campaign
ORDER BY date, source, medium, campaign
