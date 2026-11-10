-- title: Every column and nested field in one daily table
-- max_rows: 120
SELECT field_path, data_type
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce`.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS
WHERE table_name = 'events_20201101'
ORDER BY field_path
