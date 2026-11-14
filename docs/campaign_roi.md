# Campaign ROI by channel and campaign

Two tables answer "what did each paid campaign and channel return for its spend?":

| Table | Grain | Use |
|---|---|---|
| `marts.fct_campaign_roi` | one (model, campaign) | Rank and compare campaigns. |
| `marts.fct_channel_roi` | one (model, channel) | Compare the five paid channels. Built only from `fct_campaign_roi`, so the two cannot disagree. |

## Measures

| Measure | Definition |
|---|---|
| `spend_usd` | Ad spend from `stg_ad_spend`. The same under every model. |
| `attributed_orders` | Orders credited to the campaign's sessions (fractions under linear and time decay). |
| `attributed_revenue_usd` | Net revenue credited to those sessions. |
| `roas` | Return on ad spend: revenue / spend. 2.0 means $2 of revenue per $1 spent. |
| `roi` | (revenue - spend) / spend. 0 is break-even; -1 means no revenue at all. |
| `cpa_usd` | Cost per acquisition: spend / attributed orders. Empty when a campaign got no orders. |
| `profit_usd` | Revenue - spend. Revenue, not margin: product costs are not in the data. |
| `revenue_per_click` | Revenue / clicks bought. |

## The `model` column: five revenue bases

`first_touch`, `last_touch`, `linear` and `time_decay` credit **net revenue of CRM orders** to the campaign
(`fct_attribution_credits`, rows with an `ad_campaign_key`). See `docs/attribution.md`.

`ga4_session` credits every **GA4 purchase to the campaign of its own session** (`fct_sessions`). It needs neither the
CRM nor identity resolution.

Why both: `ga4_session` credits a purchase only to the campaign of the session in which it happened. The four models look
back over the customer's journey (30 days, all linked devices) and so also credit campaigns that came earlier in it.
The gap between `ga4_session` and the four models is therefore the value of assists and cross-device journeys: in the
data, Paid Search ROAS is about 0.37 on `ga4_session` and about 0.8 under the four models. Two effects pull in
opposite directions: the CRM covers only about 81% of GA4 purchases (lowers the four models), while the journey
look-back credits earlier touches (raises them). GA4 purchase revenue has no refunds, the CRM figure is net of them.

## Caveats

- **Spend is synthetic** (assumed cost per click, see `docs/synthetic_data.md`). The method is real; the ROAS, ROI and CPA
  amounts are not results of a real advertiser.
- Email ROAS is in the hundreds because the synthetic cost per email click is a few cents; treat it as an artifact of the assumed cost, not a finding.
- Paid channels earn few last-touch orders because most journeys cannot be traced beyond one device; read
  differences between models as the effect of the rule, not as a verdict on the channel.
- A campaign with spend but no credited order stays in the table with zero revenue and ROI of -1.

## Checks

`assert_campaign_roi_ties_out` fails the build if: spend or clicks differ from `stg_ad_spend`, a campaign is missing,
credited orders or revenue differ from `fct_attribution_credits`, the `ga4_session` rows differ from the paid
sessions, the channel table differs from the campaign table, or a model is missing.
Key uniqueness of both tables is in `assert_attribution_keys_are_unique`.
