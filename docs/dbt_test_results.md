# dbt test results

Recorded from `dbt/target/run_results.json` (generated 2026-11-18T18:21:11.494545Z, dbt 1.12.6). Regenerate with `uv run python -m src.dbt_results --run`.

**Result: ALL TESTS PASSED** - 334 of 334 passed, 0 warnings, 0 failures, 0 errors.

## By test type

| Test type | Tests | pass | warn | fail | error |
|---|---|---|---|---|---|
| unique | 19 | 19 | 0 | 0 | 0 |
| not_null | 224 | 224 | 0 | 0 | 0 |
| relationships | 18 | 18 | 0 | 0 | 0 |
| accepted_values | 43 | 43 | 0 | 0 | 0 |
| singular | 30 | 30 | 0 | 0 | 0 |
| **Total** | 334 | 334 | 0 | 0 | 0 |

What each type protects:

- `unique` and `not_null`: keys identify exactly one row and required fields are filled, so joins cannot double or drop rows.
- `relationships`: every customer, order and transaction id points to a row that exists in the table it refers to.
- `accepted_values`: categories (channel group, order status, match status, link rule) stay inside the documented list.
- `singular`: business rules written as SQL that must return no rows, such as order totals tying out between layers.

## By model

| Model or source | unique / not_null / relationships / accepted_values / singular | Tests | Passed | Not passed |
|---|---|---|---|---|
| `dim_customer_segments` | 2 / 5 / 0 / 1 / 0 | 8 | 8 | 0 |
| `dim_customers` | 1 / 10 / 1 / 4 / 6 | 22 | 22 | 0 |
| `fct_attribution_by_channel` | 0 / 4 / 0 / 2 / 1 | 7 | 7 | 0 |
| `fct_attribution_checks` | 0 / 7 / 0 / 1 / 2 | 10 | 10 | 0 |
| `fct_attribution_credits` | 0 / 10 / 1 / 3 / 5 | 19 | 19 | 0 |
| `fct_attribution_journeys` | 1 / 9 / 1 / 0 / 0 | 11 | 11 | 0 |
| `fct_attribution_model_comparison` | 1 / 16 / 0 / 2 / 0 | 19 | 19 | 0 |
| `fct_campaign_cpa` | 0 / 8 / 1 / 2 / 2 | 13 | 13 | 0 |
| `fct_campaign_roi` | 0 / 9 / 1 / 2 / 3 | 15 | 15 | 0 |
| `fct_channel_cpa` | 0 / 8 / 0 / 2 / 2 | 12 | 12 | 0 |
| `fct_channel_roi` | 0 / 8 / 0 / 2 / 2 | 12 | 12 | 0 |
| `fct_customer_clv` | 1 / 15 / 1 / 0 / 2 | 19 | 19 | 0 |
| `fct_customer_rfm` | 1 / 10 / 1 / 3 / 2 | 17 | 17 | 0 |
| `fct_customer_segments` | 1 / 11 / 2 / 1 / 2 | 17 | 17 | 0 |
| `fct_orders` | 1 / 14 / 1 / 4 / 8 | 28 | 28 | 0 |
| `fct_sessions` | 1 / 14 / 1 / 4 / 7 | 27 | 27 | 0 |
| `int_conversion_touchpoints` | 0 / 9 / 2 / 1 / 3 | 15 | 15 | 0 |
| `int_ga4__sessions` | 1 / 7 / 0 / 1 / 0 | 9 | 9 | 0 |
| `stg_ad_spend` | 1 / 10 / 0 / 1 / 3 | 15 | 15 | 0 |
| `stg_crm__customers` | 2 / 8 / 0 / 0 / 2 | 12 | 12 | 0 |
| `stg_crm__orders` | 1 / 8 / 2 / 2 / 4 | 17 | 17 | 0 |
| `stg_ga4__events` | 0 / 6 / 0 / 1 / 2 | 9 | 9 | 0 |
| `stg_ga4__purchases` | 1 / 5 / 0 / 1 / 2 | 9 | 9 | 0 |
| `stg_identity__links` | 1 / 5 / 1 / 2 / 3 | 12 | 12 | 0 |
| `stg_segment__identifies` | 1 / 4 / 1 / 0 / 1 | 7 | 7 | 0 |
| `stg_segment__tracks` | 1 / 4 / 1 / 1 / 1 | 8 | 8 | 0 |

A singular test that reads several models is counted under each of them.

## Singular tests (business rules)

| Test | Models read | Rows returned | Status |
|---|---|---|---|
| `assert_ad_spend_inside_ga4_window` | stg_ad_spend | 0 | pass |
| `assert_app_orders_have_no_transaction_id` | stg_crm__orders | 0 | pass |
| `assert_attribution_checks_all_pass` | fct_attribution_checks | 0 | pass |
| `assert_attribution_credits_conserve_orders_and_revenue` | fct_attribution_credits, fct_orders | 0 | pass |
| `assert_attribution_follows_its_rules` | fct_attribution_credits, int_conversion_touchpoints | 0 | pass |
| `assert_attribution_keys_are_unique` | fct_attribution_by_channel, fct_attribution_checks, fct_attribution_credits, fct_campaign_cpa, fct_campaign_roi, fct_channel_cpa, fct_channel_roi, int_conversion_touchpoints | 0 | pass |
| `assert_campaign_roi_ties_out` | fct_attribution_credits, fct_campaign_roi, fct_channel_roi, fct_sessions, stg_ad_spend | 0 | pass |
| `assert_clv_covers_the_buyers_and_ties_to_history` | dim_customers, fct_customer_clv | 0 | pass |
| `assert_clv_prediction_is_consistent` | fct_customer_clv | 0 | pass |
| `assert_cpa_ties_out` | fct_attribution_credits, fct_campaign_cpa, fct_campaign_roi, fct_channel_cpa, fct_orders | 0 | pass |
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
| `assert_rfm_covers_exactly_the_buyers` | dim_customers, fct_customer_rfm | 0 | pass |
| `assert_rfm_scores_follow_the_values` | fct_customer_rfm | 0 | pass |
| `assert_segment_rules_hold` | fct_customer_segments | 0 | pass |
| `assert_segments_cover_every_customer` | dim_customers, fct_customer_segments | 0 | pass |
| `assert_session_revenue_matches_purchases` | fct_sessions, stg_ga4__purchases | 0 | pass |
| `assert_session_values_make_sense` | fct_sessions | 0 | pass |
| `assert_sessions_cover_all_events` | fct_sessions, stg_ga4__events | 0 | pass |
| `assert_touchpoints_belong_to_the_journey` | fct_orders, int_conversion_touchpoints, stg_identity__links | 0 | pass |
| `assert_web_orders_have_ga4_purchase_value` | stg_crm__orders, stg_ga4__purchases | 0 | pass |

## Warnings and failures

None.

A `warn` is a test configured with `severity: warn` (for example the device category list): the build continues, but the rows should be looked at.
