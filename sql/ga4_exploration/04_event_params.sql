-- title: Keys inside event_params and the value type each uses
-- max_rows: 40
SELECT
  ep.key AS param_key,
  COUNT(*) AS occurrences,
  COUNTIF(ep.value.string_value IS NOT NULL) AS as_string,
  COUNTIF(ep.value.int_value IS NOT NULL) AS as_int,
  COUNTIF(ep.value.float_value IS NOT NULL OR ep.value.double_value IS NOT NULL) AS as_float
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`, UNNEST(event_params) AS ep
GROUP BY param_key
ORDER BY occurrences DESC
LIMIT 40
