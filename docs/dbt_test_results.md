# dbt test results

Recorded from `dbt/target/run_results.json` (generated 2026-11-13T09:14:02.056394Z, dbt 1.12.6). Regenerate with `uv run python -m src.dbt_results --run`.

**Result: ALL TESTS PASSED** - 153 of 153 passed, 0 warnings, 0 failures, 0 errors.

## By test type

| Test type | Tests | pass | warn | fail | error |
|---|---|---|---|---|---|
| unique | 12 | 12 | 0 | 0 | 0 |
| not_null | 95 | 95 | 0 | 0 | 0 |
| relationships | 8 | 8 | 0 | 0 | 0 |
| accepted_values | 21 | 21 | 0 | 0 | 0 |
| singular | 17 | 17 | 0 | 0 | 0 |
| **Total** | 153 | 153 | 0 | 0 | 0 |

What each type protects:

- `unique` and `not_null`: keys identify exactly one row and required fields are filled, so joins cannot double or drop rows.
- `relationships`: every customer, order and transaction id points to a row that exists in the table it refers to.
- `accepted_values`: categories (channel group, order status, match status, link rule) stay inside the documented list.
- `singular`: business rules written as SQL that must return no rows, such as order totals tying out between layers.

## By model

| Model or source | unique / not_null / relationships / accepted_values / singular | Tests | Passed | Not passed |
|---|---|---|---|---|
| `dim_customers` | 1 / 10 / 1 / 4 / 3 | 19 | 19 | 0 |
| `fct_orders` | 1 / 14 / 1 / 4 / 5 | 25 | 25 | 0 |
| `fct_sessions` | 1 / 14 / 1 / 4 / 6 | 26 | 26 | 0 |
| `int_ga4__sessions` | 1 / 7 / 0 / 1 / 0 | 9 | 9 | 0 |
| `stg_ad_spend` | 1 / 10 / 0 / 1 / 2 | 14 | 14 | 0 |
| `stg_crm__customers` | 2 / 8 / 0 / 0 / 2 | 12 | 12 | 0 |
| `stg_crm__orders` | 1 / 8 / 2 / 2 / 4 | 17 | 17 | 0 |
| `stg_ga4__events` | 0 / 6 / 0 / 1 / 2 | 9 | 9 | 0 |
| `stg_ga4__purchases` | 1 / 5 / 0 / 1 / 2 | 9 | 9 | 0 |
| `stg_identity__links` | 1 / 5 / 1 / 2 / 2 | 11 | 11 | 0 |
| `stg_segment__identifies` | 1 / 4 / 1 / 0 / 1 | 7 | 7 | 0 |
| `stg_segment__tracks` | 1 / 4 / 1 / 1 / 1 | 8 | 8 | 0 |

A singular test that reads several models is counted under each of them.

## Singular tests (business rules)

| Test | Models read | Rows returned | Status |
|---|---|---|---|
| `assert_ad_spend_inside_ga4_window` | stg_ad_spend | 0 | pass |
| `assert_app_orders_have_no_transaction_id` | stg_crm__orders | 0 | pass |
| `assert_customer_orders_tie_to_orders_mart` | dim_customers, fct_orders | 0 | pass |
| `assert_customer_profile_is_consistent` | dim_customers, stg_crm__customers | 0 | pass |
| `assert_customer_sessions_tie_to_sessions_mart` | dim_customers, fct_sessions, stg_identity__links | 0 | pass |
| `assert_identify_hash_matches_customer` | stg_crm__customers, stg_segment__identifies | 0 | pass |
| `assert_identity_devices_exist_in_ga4` | stg_ga4__events, stg_identity__links | 0 | pass |
| `assert_matched_orders_have_a_session` | fct_orders, fct_sessions | 0 | pass |
| `assert_order_history_is_consistent` | fct_orders | 0 | pass |
| `assert_orders_cover_crm_orders` | fct_orders, stg_crm__orders | 0 | pass |
| `assert_orders_match_segment_tracks` | fct_orders, stg_segment__tracks | 0 | pass |
| `assert_paid_sessions_match_ad_spend` | fct_sessions, stg_ad_spend | 0 | pass |
| `assert_refunds_match_status` | stg_crm__orders | 0 | pass |
| `assert_session_revenue_matches_purchases` | fct_sessions, stg_ga4__purchases | 0 | pass |
| `assert_session_values_make_sense` | fct_sessions | 0 | pass |
| `assert_sessions_cover_all_events` | fct_sessions, stg_ga4__events | 0 | pass |
| `assert_web_orders_have_ga4_purchase_value` | stg_crm__orders, stg_ga4__purchases | 0 | pass |

## Warnings and failures

None.

A `warn` is a test configured with `severity: warn` (for example the device category list): the build continues, but the rows should be looked at.
