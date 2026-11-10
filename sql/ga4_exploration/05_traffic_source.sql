-- title: User-level traffic source (how each user was first acquired)
-- max_rows: 30
SELECT
  traffic_source.source AS source,
  traffic_source.medium AS medium,
  traffic_source.name AS campaign,
  COUNT(DISTINCT user_pseudo_id) AS users
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
GROUP BY source, medium, campaign
ORDER BY users DESC
LIMIT 30
