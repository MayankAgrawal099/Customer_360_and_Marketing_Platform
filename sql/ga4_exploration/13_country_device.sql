-- title: Top countries and device categories (by users)
-- max_rows: 20
SELECT 'country' AS dimension, geo.country AS value, COUNT(DISTINCT user_pseudo_id) AS users
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
GROUP BY value
QUALIFY ROW_NUMBER() OVER (ORDER BY users DESC) <= 10
UNION ALL
SELECT 'device' AS dimension, device.category AS value, COUNT(DISTINCT user_pseudo_id) AS users
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
GROUP BY value
ORDER BY dimension, users DESC
