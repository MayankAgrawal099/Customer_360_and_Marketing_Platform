# Marts

Business-ready tables, built as tables in the `marts` dataset.

| Model | Grain | Notes |
|---|---|---|
| `fct_sessions` | one GA4 session | Channel, purchases and customer per session. Built from `int_ga4__sessions` (intermediate). |
| `fct_orders` | one CRM order | Order history per customer and, for web orders, the GA4 session and channel that produced the order. |
| `dim_customers` | one CRM customer | Profile, order summary, linked GA4 devices and their sessions. All customers, buyers or not. |
| `fct_customer_rfm` | one buyer | Recency, frequency, monetary and 1-5 scores. Buyers only. |
| `fct_customer_clv` | one buyer | Historical net revenue plus predicted 90-day and 12-month revenue, and 12-month CLV. Buyers only. |
| `dim_customer_segments` | one segment | Segment definitions: rule, plain-words definition, recommended action. |
| `fct_customer_segments` | one CRM customer | Segment, RFM scores and value for every customer. |
| `fct_attribution_credits` | one (order, model) | Which channel gets each order under first touch and last touch. Built from `int_conversion_touchpoints`. |
| `fct_attribution_by_channel` | one (model, channel) | Credited orders and net revenue by channel, with shares. |
| `fct_attribution_journeys` | one CRM order | Journey length and where first and last touch disagree. |
| `fct_attribution_model_comparison` | one channel | The four models side by side: revenue, spread, introduces or closes. |
| `fct_attribution_checks` | one (check, model) | Attribution sanity checks recorded as a table; the build fails if any fails. |
| `fct_campaign_roi` | one (model, campaign) | Spend, credited orders and revenue, ROAS, ROI and CPA per paid campaign, under the four models and a GA4 same-session benchmark. |
| `fct_channel_roi` | one (model, channel) | The same measures rolled up to the five paid channels. |

Channel rules live in one macro, `dbt/macros/channel_group.sql`. `tests/test_dbt_sessions.py` runs the macro and `src/synthetic/channels.py` on the same inputs and fails if they ever differ.

Run (repository root)
```
uv run dbt run  --project-dir dbt --profiles-dir dbt --select +fct_sessions +fct_orders +dim_customers +fct_customer_rfm +fct_customer_clv +fct_customer_segments +fct_attribution_journeys +fct_attribution_model_comparison +fct_attribution_checks +fct_campaign_roi +fct_channel_roi
uv run dbt test --project-dir dbt --profiles-dir dbt --select +fct_sessions +fct_orders +dim_customers +fct_customer_rfm +fct_customer_clv +fct_customer_segments +fct_attribution_journeys +fct_attribution_model_comparison +fct_attribution_checks +fct_campaign_roi +fct_channel_roi
```
