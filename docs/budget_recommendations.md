# Budget recommendations

The Tableau attribution, ROI and CPA dashboard ends with a recommendation for every paid channel and every paid campaign.
It comes from `sql/tableau/budget_recommendations.sql`, which reads `fct_channel_roi` and `fct_campaign_roi` (see
`docs/campaign_roi.md`). One row per channel (`level = 'Channel'`) and one per campaign (`level = 'Campaign'`).

## The views a recommendation rests on

A campaign's ROAS (revenue / spend) is read under **five bases**: first touch, last touch, linear, time decay (the four
attribution models, `docs/attribution.md`) and `ga4_session` (the narrowest view, `docs/campaign_roi.md`). The rule looks at
the **lowest** and **highest** ROAS across the five, so one favourable model cannot carry a recommendation.

| Column | Meaning |
|---|---|
| `roas_low`, `roas_high` | Lowest and highest ROAS across the five bases |
| `roas_models_avg` | Average ROAS of the four attribution models only |
| `orders_models_avg`, `revenue_models_avg` | Average attributed orders and net revenue of the four attribution models |

## Rules, applied in this order

| # | Recommendation | Condition | Suggested change |
|---|---|---|---|
| 1 | Not enough data | fewer than 5 attributed orders on average across the four models | 0% |
| 2 | Hold | the channel is Email (its cost per click is assumed, so its ROAS is an artifact, not evidence) | 0% |
| 3 | Increase | `roas_low` is at least 1.5: a return of $1.50 or more per $1 under every view | +20% |
| 4 | Reduce | `roas_high` is below 1: no view says the spend pays back | -30% |
| 5 | Hold | anything else: the views disagree, or the return is modest | 0% |

The thresholds (5 orders, 1.5, 1.0, +20%, -30%) sit in the `rules` CTE at the top of the SQL file.

## How to read it

- ROAS is revenue, not profit: product costs are not in the data. The 1.5 bar for Increase leaves room for them.
- The suggested change is a rule of thumb for a test, not a forecast. `proposed_spend_usd` is today's spend times
  (1 + suggested change).
- Spend is synthetic (assumed cost per click, `docs/synthetic_data.md`): the method is real, the dollar amounts are not.
- A campaign that wins few orders is never ranked as a winner or a loser: Not enough data is shown instead.

## Checks

`tests/test_tableau_roi_export.py` runs the real SQL on hand-built tables: every rule, the proposed spend, the ROAS range,
that channel spend equals campaign spend, and that the joins do not duplicate rows.
