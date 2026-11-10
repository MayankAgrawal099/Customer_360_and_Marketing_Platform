-- title: Size and date range of the sample
-- max_rows: 5
SELECT
  MIN(PARSE_DATE('%Y%m%d', event_date)) AS first_day,
  MAX(PARSE_DATE('%Y%m%d', event_date)) AS last_day,
  COUNT(DISTINCT event_date) AS days,
  COUNT(*) AS events,
  COUNT(DISTINCT user_pseudo_id) AS pseudo_users,
  COUNT(DISTINCT user_id) AS distinct_user_ids,
  COUNTIF(user_id IS NOT NULL) AS events_with_user_id,
  COUNTIF(user_pseudo_id IS NULL) AS events_without_pseudo_id
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
