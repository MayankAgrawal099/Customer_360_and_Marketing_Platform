# Marts

Business-ready tables, built as tables in the `marts` dataset.

| Model | Grain | Notes |
|---|---|---|
| `fct_sessions` | one GA4 session | Channel, purchases and customer per session. Built from `int_ga4__sessions` (intermediate). |
| `fct_orders` | one CRM order | Order history per customer and, for web orders, the GA4 session and channel that produced the order. |

Channel rules live in one macro, `dbt/macros/channel_group.sql`. `tests/test_dbt_sessions.py` runs the macro and `src/synthetic/channels.py` on the same inputs and fails if they ever differ.

Run (repository root)
```
uv run dbt run  --project-dir dbt --profiles-dir dbt --select +fct_sessions +fct_orders
uv run dbt test --project-dir dbt --profiles-dir dbt --select +fct_sessions +fct_orders
```
