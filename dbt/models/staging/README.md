# Staging models

One model per raw table, with light cleaning only: rename, cast, flatten. No business logic and no joins
between sources (the identity link is a separate source, not a join).

| Model | Built from | Grain | Materialised |
|---|---|---|---|
| `stg_ga4__events` | `raw.ga4_events` | one GA4 event | table (about 1.3 GB scan, every later model starts here) |
| `stg_ga4__purchases` | `stg_ga4__events` | one valid purchase transaction | view |
| `stg_crm__customers` | `raw.crm_customers` | one customer | view |
| `stg_crm__orders` | `raw.crm_orders` | one order | view |
| `stg_ad_spend` | `raw.ad_spend` | one paid campaign per day | view |
| `stg_segment__identifies` | `raw.segment_identifies` | one identify event | view |
| `stg_segment__tracks` | `raw.segment_tracks` | one track event | view |
| `stg_identity__links` | `identity.identity_links` | one linked device | view |

Rules
- `raw.ground_truth_identity_links` is not a dbt source. It is for scoring identity resolution only, and a test fails if a model refers to it.
- Column descriptions and tests are in `_staging.yml`; sources are in `_sources.yml`.
- Tests: `unique` and `not_null` on keys, `relationships` between tables, `accepted_values` for codes, plus the singular tests in `dbt/tests/`.

Run (repository root)
```
uv run dbt run  --project-dir dbt --profiles-dir dbt --select staging
uv run dbt test --project-dir dbt --profiles-dir dbt --select staging
```
