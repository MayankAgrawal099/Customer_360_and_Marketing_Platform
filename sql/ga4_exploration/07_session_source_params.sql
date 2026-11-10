-- title: Do events carry session-level source, medium or campaign?
-- max_rows: 15
SELECT
  event_name,
  COUNT(*) AS events,
  COUNTIF((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'source') IS NOT NULL) AS with_source,
  COUNTIF((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'medium') IS NOT NULL) AS with_medium,
  COUNTIF((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'campaign') IS NOT NULL) AS with_campaign,
  COUNTIF((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_referrer') IS NOT NULL) AS with_referrer,
  COUNTIF((SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') IS NOT NULL) AS with_page_location
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
GROUP BY event_name
ORDER BY events DESC
LIMIT 15
