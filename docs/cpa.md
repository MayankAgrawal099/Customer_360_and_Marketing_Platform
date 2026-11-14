# Cost per acquisition by channel and campaign

| Table | Grain | Use |
|---|---|---|
| `marts.fct_campaign_cpa` | one (model, campaign) | Find the cheapest and the most expensive campaigns. |
| `marts.fct_channel_cpa` | one (model, channel) | Compare the five paid channels. Built only from `fct_campaign_cpa`. |

Both build on `fct_campaign_roi` (spend, orders, revenue; see `docs/campaign_roi.md`) and add who the orders came from.

## Measures

| Measure | Definition |
|---|---|
| `cpa_usd` | Cost per acquisition: spend / attributed orders. The cost to win one **order**. |
| `new_customers` | Credited first orders (`fct_orders.is_first_order`): customers won for the first time. Fractions under linear and time decay. |
| `repeat_orders` | Attributed orders - new customers. |
| `cac_usd` | Customer acquisition cost: spend / new customers. The cost to win one **new customer**. |
| `avg_order_value_usd` | Credited revenue / credited orders. |
| `cpa_to_aov` | `cpa_usd` / average order value. Below 1 the order's own revenue covers the cost of winning it; above 1 it does not. |
| `has_enough_orders` | At least 5 attributed orders. One order moves the CPA of a smaller campaign a lot, so those are not ranked. |
| `cpa_rank` | 1 = cheapest cost per order among rows with enough orders, within one model. |
| `cpa_vs_channel` | Campaign CPA / its channel's CPA (same model). Below 1 the campaign beats its channel. |

## Reading it

- `cpa_usd` and `cac_usd` differ whenever some credited orders are repeat orders; the gap shows how much of a channel's
  results is existing customers coming back.
- `ga4_session` rows have a CPA but no `new_customers` or `cac_usd`: a GA4 purchase has no customer id.
- Compare a campaign's CPA across the four models to see how much the answer depends on the attribution rule.
- `cpa_to_aov` is on revenue, not profit (product costs are not in the data), so it flatters every channel.

## Caveats

- **Spend is synthetic** (assumed cost per click, `docs/synthetic_data.md`). The method is real; the amounts are not.
- Email's CPA is a few cents because the assumed cost per email click is tiny.
- A campaign with spend and no credited order has no CPA (empty, not zero).

## Checks

`assert_cpa_ties_out` fails the build if: the campaign rows, spend, orders or revenue differ from `fct_campaign_roi`;
new customers differ from the credited first orders, or exceed orders; `cpa_usd` is not spend / orders; `ga4_session`
has new customers; or the channel table differs from the campaign table. Key uniqueness of both tables is in
`assert_attribution_keys_are_unique`.
