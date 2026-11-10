-- title: Purchase events: counts, revenue and data-quality flags
-- max_rows: 5
SELECT
  COUNT(*) AS purchase_events,
  COUNT(DISTINCT ecommerce.transaction_id) AS distinct_transactions,
  COUNTIF(ecommerce.transaction_id IS NULL OR ecommerce.transaction_id = '(not set)') AS missing_transaction_id,
  COUNT(DISTINCT user_pseudo_id) AS buyers,
  ROUND(SUM(ecommerce.purchase_revenue_in_usd), 2) AS revenue_usd,
  ROUND(AVG(ecommerce.purchase_revenue_in_usd), 2) AS avg_order_usd,
  COUNTIF(ecommerce.purchase_revenue_in_usd IS NULL) AS null_revenue,
  COUNTIF(ecommerce.purchase_revenue_in_usd = 0) AS zero_revenue
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name = 'purchase'
