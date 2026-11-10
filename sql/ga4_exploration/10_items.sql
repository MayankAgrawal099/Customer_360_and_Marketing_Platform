-- title: Purchased items by category
-- max_rows: 15
SELECT
  item.item_category AS category,
  COUNT(*) AS item_lines,
  SUM(item.quantity) AS units,
  ROUND(SUM(item.item_revenue_in_usd), 2) AS revenue_usd,
  ROUND(AVG(item.price_in_usd), 2) AS avg_price_usd
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`, UNNEST(items) AS item
WHERE event_name = 'purchase'
GROUP BY category
ORDER BY revenue_usd DESC
LIMIT 15
