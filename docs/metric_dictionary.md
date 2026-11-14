# Metric dictionary

One definition for every metric used in the marts and the dashboards. Each row says what the metric means, how it is
calculated, and the column that holds it (`table.column`, in the `marts` dataset). A test (`tests/test_metric_dictionary.py`)
fails if a column named here does not exist, so this page cannot drift from the tables.

Conventions used throughout:

- **Revenue is net revenue** (order value minus refunds) unless a row says gross. GA4 purchase revenue has no refunds.
- **Dates are measured to `as_of_date`**: the day after the latest order in the data, never today's date.
- **Buyer** = a customer with at least one order. Customers without orders appear in `dim_customers` but have no RFM or CLV.
- **Ad spend is synthetic** (assumed cost per click, `docs/synthetic_data.md`). The ROI and CPA formulas are real; the dollar amounts are not.

## Customer value

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| Orders | CRM orders placed by the customer | count of orders | `dim_customers.orders` |
| Gross revenue | Order value before refunds | sum of order value | `dim_customers.gross_revenue_usd` |
| Net revenue | Order value after refunds | gross revenue - refunds | `dim_customers.net_revenue_usd` |
| Average order value (AOV) | Typical size of an order | gross revenue / orders | `dim_customers.avg_order_value_usd` |
| Buyer | Has placed at least one order | orders > 0 | `dim_customers.is_buyer` |
| Repeat buyer | Has placed two or more orders | orders >= 2 | `dim_customers.is_repeat_buyer` |
| Repeat orders | Orders after the first | orders - 1 | `fct_customer_clv.repeat_orders` |

## RFM (recency, frequency, monetary)

Buyers only. Scores run 1 (worst) to 5 (best). Details in `docs/customer_segments.md`.

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| Recency | Days since the last order (smaller is better) | `as_of_date` - last order date | `fct_customer_rfm.recency_days` |
| Frequency | Number of orders | count of orders | `fct_customer_rfm.frequency` |
| Monetary | Net revenue to date | sum of net revenue | `fct_customer_rfm.monetary_usd` |
| R score | Recency quintile, 5 = most recent | ceil(5 x share of buyers at or below this value); ties share a score | `fct_customer_rfm.r_score` |
| F score | Frequency band | 1, 2, 3, 4 orders score 1-4; 5 or more score 5 | `fct_customer_rfm.f_score` |
| M score | Monetary quintile, 5 = highest spend | ceil(5 x share of buyers at or below this value); ties share a score | `fct_customer_rfm.m_score` |
| RFM code | The three scores together, e.g. 521 | R, F, M written as text | `fct_customer_rfm.rfm_code` |
| RFM total | Overall score, 3 to 15 | R + F + M | `fct_customer_rfm.rfm_total` |
| Segment | One of nine named groups, first matching rule wins | rules on the R, F and M scores | `fct_customer_segments.segment` |

## Customer lifetime value (CLV)

Buyers only. Gamma-Poisson shrinkage: a customer's own behaviour is pulled towards the population's until they have
about three months of history. No churn is modelled and the data covers about three months, so the 12-month figure is an
**upper estimate**; the 90-day figure stays within what the data has seen.

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| Historical net revenue | What the customer has already brought in | sum of net revenue | `fct_customer_clv.historical_net_revenue_usd` |
| Expected repeat rate | Repeat orders per day, shrunk towards all buyers | (own repeat orders + 90 x population rate) / (own days observed + 90) | `fct_customer_clv.expected_repeat_rate_per_day` |
| Expected order value | Average order value, shrunk towards all buyers | (own net revenue + 3 x population AOV) / (own orders + 3) | `fct_customer_clv.expected_aov_usd` |
| Predicted orders, 90 days | Expected orders in the next 90 days | rate x 90 | `fct_customer_clv.predicted_orders_90d` |
| Predicted revenue, 90 days | Expected net revenue in the next 90 days | rate x 90 x expected order value | `fct_customer_clv.predicted_revenue_90d_usd` |
| Predicted orders, 12 months | Expected orders in the next 365 days | rate x 365 | `fct_customer_clv.predicted_orders_12m` |
| Predicted revenue, 12 months | Expected net revenue in the next 365 days | rate x 365 x expected order value | `fct_customer_clv.predicted_revenue_12m_usd` |
| CLV, 12 months | Value to date plus the next year | historical net revenue + predicted revenue, 12 months | `fct_customer_clv.clv_12m_usd` |

## Attribution

Applies to the CRM orders. A journey is the sessions on the purchasing device or any linked device in the 30 days before
the order. Only touchpoints with a known source can earn credit (Direct, Self Referral, Unassigned and Other cannot).
Every model gives each order exactly one unit of credit. Details in `docs/attribution.md`.

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| Credit | Share of one order given to a touchpoint | first / last touch: 1 to one touchpoint; linear: 1/n each; time decay: weight / total weight, weight = 0.5 ^ (days before order / 7) | `fct_attribution_credits.credit` |
| Credited revenue | Revenue a touchpoint receives | credit x net revenue of the order | `fct_attribution_credits.credited_revenue_usd` |
| Attributed orders | Orders credited to a channel under a model (fractions under linear and time decay) | sum of credit | `fct_attribution_by_channel.attributed_orders` |
| Attributed revenue | Net revenue credited to a channel under a model | sum of credited revenue | `fct_attribution_by_channel.attributed_revenue_usd` |
| Share of orders | Channel's part of all orders under the model | channel orders / all orders | `fct_attribution_by_channel.share_of_orders` |
| Share of revenue | Channel's part of all revenue under the model | channel revenue / all revenue | `fct_attribution_by_channel.share_of_revenue` |
| Journey length | Sessions in an order's journey | count of touchpoints | `fct_attribution_journeys.touchpoints` |
| Revenue spread | How much the choice of model matters for a channel | highest - lowest revenue across the four models | `fct_attribution_model_comparison.revenue_spread_usd` |
| Introducing gap | How much better a channel introduces than closes | first-touch revenue - last-touch revenue | `fct_attribution_model_comparison.introducing_gap_usd` |
| Role | Introduces or Closes when the gap is at least $25 and 5% of the channel's average revenue | rule on the introducing gap | `fct_attribution_model_comparison.role` |

## Campaign ROI

Rows exist per model (`first_touch`, `last_touch`, `linear`, `time_decay`, and `ga4_session`, which credits a GA4 purchase
only to the campaign of its own session). Details in `docs/campaign_roi.md`.

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| Spend | Ad spend in USD (synthetic) | sum of daily spend | `fct_campaign_roi.spend_usd` |
| Cost per click | What one click cost | spend / clicks | `fct_campaign_roi.cost_per_click` |
| Attributed revenue | Net revenue credited to the campaign | as in Attribution | `fct_campaign_roi.attributed_revenue_usd` |
| Profit | Revenue left after the ad spend (not margin: product costs are not in the data) | revenue - spend | `fct_campaign_roi.profit_usd` |
| ROAS | Return on ad spend: dollars of revenue per dollar spent | revenue / spend | `fct_campaign_roi.roas` |
| ROI | Return after the spend. 0 = break-even, -1 = no revenue | (revenue - spend) / spend | `fct_campaign_roi.roi` |
| Revenue per click | Revenue won per click bought | revenue / clicks | `fct_campaign_roi.revenue_per_click` |
| Channel ROAS | The same, for a whole channel | channel revenue / channel spend | `fct_channel_roi.roas` |
| Channel ROI | The same, for a whole channel | (revenue - spend) / spend | `fct_channel_roi.roi` |

## Cost per acquisition (CPA)

Details in `docs/cpa.md`.

| Metric | Meaning | Formula | Where |
|---|---|---|---|
| CPA | Cost to win one order. Empty when there are no orders | spend / attributed orders | `fct_campaign_cpa.cpa_usd` |
| New customers | Credited first orders (empty under `ga4_session`) | sum of credit on first orders | `fct_campaign_cpa.new_customers` |
| CAC | Customer acquisition cost: cost to win one new customer | spend / new customers | `fct_campaign_cpa.cac_usd` |
| CPA to AOV | Below 1 the order's own revenue covers what it cost to win | CPA / average order value | `fct_campaign_cpa.cpa_to_aov` |
| CPA rank | 1 = cheapest cost per order among rows with 5 or more orders, within a model | rank by CPA | `fct_campaign_cpa.cpa_rank` |
| CPA vs channel | Below 1 the campaign beats its channel | campaign CPA / channel CPA | `fct_campaign_cpa.cpa_vs_channel` |
| Channel CPA | CPA for a whole channel | channel spend / channel orders | `fct_channel_cpa.cpa_usd` |
| Channel CAC | CAC for a whole channel | channel spend / channel new customers | `fct_channel_cpa.cac_usd` |

## Reading these metrics together

- ROAS and CPA use the same spend and the same credited orders; ROAS looks at revenue, CPA at order count. A campaign with
  ROAS below 1 is losing money on revenue alone.
- Compare a campaign across the four models before trusting a single figure; `ga4_session` is the narrowest view because
  it ignores earlier touches in the journey.
- Do not compare a CPA ranked on 5 orders with one on 50: the small one moves a lot with a single order.
