-- file: purchases.csv
-- One row per purchase (first occurrence of each transaction_id), with revenue above zero.
SELECT
  ecommerce.transaction_id AS transaction_id,
  user_pseudo_id,
  TIMESTAMP_MICROS(event_timestamp) AS event_ts,
  ecommerce.purchase_revenue_in_usd AS revenue_usd,
  ecommerce.total_item_quantity AS item_quantity
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE event_name = 'purchase'
  AND user_pseudo_id IS NOT NULL
  AND ecommerce.transaction_id IS NOT NULL
  AND ecommerce.transaction_id != '(not set)'
  AND ecommerce.purchase_revenue_in_usd > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY ecommerce.transaction_id ORDER BY event_timestamp) = 1
