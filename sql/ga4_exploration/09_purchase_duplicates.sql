-- title: Transaction IDs that appear on more than one purchase event
-- max_rows: 10
SELECT ecommerce.transaction_id AS transaction_id, COUNT(*) AS occurrences, COUNT(DISTINCT user_pseudo_id) AS users
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name = 'purchase' AND ecommerce.transaction_id IS NOT NULL
GROUP BY transaction_id
HAVING COUNT(*) > 1
ORDER BY occurrences DESC
LIMIT 10
