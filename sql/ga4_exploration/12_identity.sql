-- title: How many anonymous users ever have a logged-in user_id?
-- max_rows: 5
WITH u AS (
  SELECT user_pseudo_id, MAX(IF(user_id IS NOT NULL, 1, 0)) AS has_user_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  GROUP BY user_pseudo_id
)
SELECT
  COUNT(*) AS pseudo_users,
  SUM(has_user_id) AS pseudo_users_with_user_id,
  ROUND(100 * SAFE_DIVIDE(SUM(has_user_id), COUNT(*)), 2) AS pct_with_user_id
FROM u
