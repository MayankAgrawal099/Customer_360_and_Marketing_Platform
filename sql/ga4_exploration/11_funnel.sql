-- title: Sessions reaching each shopping step
-- max_rows: 10
SELECT
  event_name,
  COUNT(DISTINCT CONCAT(user_pseudo_id, '-', CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS STRING))) AS sessions
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name IN ('session_start', 'view_item', 'add_to_cart', 'begin_checkout', 'add_payment_info', 'purchase')
GROUP BY event_name
ORDER BY sessions DESC
