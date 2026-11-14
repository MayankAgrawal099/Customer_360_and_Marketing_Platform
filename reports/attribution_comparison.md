# Attribution: comparing the four models

Generated 2026-11-14 by `src/attribution_report.py` from `marts.fct_attribution_model_comparison` and `marts.fct_attribution_checks`. Method: `docs/attribution.md`.

## Do the models add up?

**ALL CHECKS PASSED**: 30 of 30 checks passed. Each model credits $344,692 of net revenue, the same as the orders, and the four totals differ by $0.

| Check | Model | Expected | Actual | Difference | Passed |
|---|---|---|---|---|---|
| `channel_table_orders_equal_orders` | first_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `channel_table_orders_equal_orders` | last_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `channel_table_orders_equal_orders` | linear | 5,120.00 | 5,120.00 | 0.00 | yes |
| `channel_table_orders_equal_orders` | time_decay | 5,120.00 | 5,120.00 | 0.00 | yes |
| `channel_table_revenue_equals_net_revenue` | first_touch | 344,691.89 | 344,691.89 | -0.00 | yes |
| `channel_table_revenue_equals_net_revenue` | last_touch | 344,691.89 | 344,691.89 | -0.00 | yes |
| `channel_table_revenue_equals_net_revenue` | linear | 344,691.89 | 344,691.89 | -0.00 | yes |
| `channel_table_revenue_equals_net_revenue` | time_decay | 344,691.89 | 344,691.89 | -0.00 | yes |
| `credited_orders_equal_orders` | first_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `credited_orders_equal_orders` | last_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `credited_orders_equal_orders` | linear | 5,120.00 | 5,120.00 | -0.00 | yes |
| `credited_orders_equal_orders` | time_decay | 5,120.00 | 5,120.00 | -0.00 | yes |
| `credited_revenue_equals_net_revenue` | first_touch | 344,691.89 | 344,691.89 | -0.00 | yes |
| `credited_revenue_equals_net_revenue` | last_touch | 344,691.89 | 344,691.89 | -0.00 | yes |
| `credited_revenue_equals_net_revenue` | linear | 344,691.89 | 344,691.89 | -0.00 | yes |
| `credited_revenue_equals_net_revenue` | time_decay | 344,691.89 | 344,691.89 | -0.00 | yes |
| `every_order_has_one_unit_of_credit` | first_touch | 0.00 | 0.00 | 0.00 | yes |
| `every_order_has_one_unit_of_credit` | last_touch | 0.00 | 0.00 | 0.00 | yes |
| `every_order_has_one_unit_of_credit` | linear | 0.00 | 0.00 | 0.00 | yes |
| `every_order_has_one_unit_of_credit` | time_decay | 0.00 | 0.00 | 0.00 | yes |
| `first_and_last_touch_have_one_row_per_order` | first_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `first_and_last_touch_have_one_row_per_order` | last_touch | 5,120.00 | 5,120.00 | 0.00 | yes |
| `four_models_present` | all | 4.00 | 4.00 | 0.00 | yes |
| `no_credit_row_outside_0_and_1` | first_touch | 0.00 | 0.00 | 0.00 | yes |
| `no_credit_row_outside_0_and_1` | last_touch | 0.00 | 0.00 | 0.00 | yes |
| `no_credit_row_outside_0_and_1` | linear | 0.00 | 0.00 | 0.00 | yes |
| `no_credit_row_outside_0_and_1` | time_decay | 0.00 | 0.00 | 0.00 | yes |
| `orders_revenue_equals_customer_profile` | all | 344,691.89 | 344,691.89 | 0.00 | yes |
| `same_revenue_under_all_models: Direct / Unknown` | all | 0.00 | 0.00 | 0.00 | yes |
| `same_revenue_under_all_models: No Touchpoint` | all | 0.00 | 0.00 | 0.00 | yes |

## Net revenue by channel

| Channel | First touch | Last touch | Linear | Time decay | Spread | Spread % | Role |
|---|---|---|---|---|---|---|---|
| Organic Search | $149,900 | $149,380 | $148,986 | $148,312 | $1,589 | 1.1% | Neutral |
| Referral | $85,050 | $85,960 | $86,152 | $86,783 | $1,734 | 2.0% | Neutral |
| Direct / Unknown | $71,923 | $71,923 | $71,923 | $71,923 | $0 | 0.0% | No known source |
| No Touchpoint | $28,995 | $28,995 | $28,995 | $28,995 | $0 | 0.0% | No known source |
| Paid Search | $6,595 | $6,240 | $6,389 | $6,387 | $355 | 5.5% | Introduces |
| Email | $1,884 | $1,821 | $1,888 | $1,929 | $108 | 5.7% | Neutral |
| Affiliate | $202 | $202 | $202 | $202 | $0 | 0.0% | Neutral |
| Organic Social | $142 | $142 | $142 | $142 | $0 | 0.0% | Neutral |
| Display | $0 | $28 | $14 | $18 | $28 | 187.7% | Closes |
| **Total** | **$344,692** | **$344,692** | **$344,692** | **$344,692** |  |  |  |

Spread is the highest minus the lowest revenue the channel gets across the four models. Role compares first and last touch: *Introduces* when first touch gives the channel at least 5% (and $25) more than last touch, *Closes* when it gives less. *No known source* rows collect orders whose journey has no source.

## Share of revenue

| Channel | First touch | Last touch | Linear | Time decay |
|---|---|---|---|---|
| Organic Search | 43.5% | 43.3% | 43.2% | 43.0% |
| Referral | 24.7% | 24.9% | 25.0% | 25.2% |
| Direct / Unknown | 20.9% | 20.9% | 20.9% | 20.9% |
| No Touchpoint | 8.4% | 8.4% | 8.4% | 8.4% |
| Paid Search | 1.9% | 1.8% | 1.9% | 1.9% |
| Email | 0.5% | 0.5% | 0.5% | 0.6% |
| Affiliate | 0.1% | 0.1% | 0.1% | 0.1% |
| Organic Social | 0.0% | 0.0% | 0.0% | 0.0% |
| Display | 0.0% | 0.0% | 0.0% | 0.0% |

## What the comparison shows

- **The choice of model moves big channels little.** Among channels with at least 1% of revenue, the largest difference between models is 5.5% of the channel's average (**Paid Search**); the largest in dollars is $1,734 (**Referral**).
- **The biggest uncertainty is missing sources, not the model.** $100,918 (29.3% of revenue) has no known source and is credited identically by all four models (Direct / Unknown and No Touchpoint).
- **Paid channels are small.** Paid Search, Display, Paid Social, Affiliate and Email together get $8,291 to $8,681 depending on the model, about 2.5% of revenue.
- **Introduces:** Paid Search. **Closes:** Display.

## How to read it

- The models differ only on orders with more than one visit that has a known source; single-visit orders get the same credit under all four.
- Linear and time decay credit fractions of an order, so channel order counts can be fractions.
- Attribution covers CRM orders (customers who can be followed across devices). GA4 purchases by visitors who are not in the CRM are not part of it.
- The data covers about three months, so the 30-day look-back and the 7-day time-decay half-life are conventions, not findings.
