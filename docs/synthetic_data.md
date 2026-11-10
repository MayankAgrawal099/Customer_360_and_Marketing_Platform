# Synthetic data: CRM, orders, ad spend and Segment-style events

The GA4 sample has no customer records, no ad spend and almost no logged-in users. These tables are
generated to fill that gap. They are **synthetic** (made with Faker and a fixed seed), but they are built
on **real GA4 facts**, so each synthetic row lines up with a real user, purchase or day.

## How it is built

```
BigQuery GA4 sample ──► src.synthetic.ga4_extract ──► data/raw/ga4_extract/*.csv   (git-ignored)
                                                       users, purchases, daily_traffic
data/raw/ga4_extract/*.csv ──► src.synthetic.generate_crm ──► data/synthetic/*
```

Run, from the repository root:

```bash
uv run python -m src.synthetic.ga4_extract        # downloads the three extract files
uv run python -m src.synthetic.generate_crm       # writes data/synthetic/
```

The seed is 42 (`src/synthetic/config.py`). The same extract gives byte-identical output every run.

## What links to what

| Synthetic table | Real GA4 fact it is built on |
|---|---|
| `crm_customers` | GA4 buyers (minus guest checkouts) and a few non-buyers who register; country, and timing from real first and last visits |
| `crm_orders` (web) | One row per real GA4 purchase: same time, same revenue, same item count; `ga_transaction_id` is the GA4 transaction ID |
| `crm_orders` (app) | Extra purchases GA4 never sees (the mobile app). They have no GA4 match |
| `ad_spend` | Real daily sessions of each paid campaign, using the session-level source, medium and campaign (Paid Search, Display, Affiliate, Email) |
| `segment_identifies` | Links a real GA4 `user_pseudo_id` (anonymousId) to a customer (userId) |
| `segment_tracks` | `Signed Up` and `Order Completed` events, sent from the server with userId only |
| `ground_truth/ground_truth_identity_links` | The true device-to-customer links, for measuring accuracy |

## Files

| File | Columns |
|---|---|
| `data/synthetic/crm_customers.csv` | customer_id, first_name, last_name, email, email_sha256, phone, country, created_at, marketing_opt_in |
| `data/synthetic/crm_orders.csv` | order_id, customer_id, order_ts, order_channel (web or app), ga_transaction_id, order_value_usd, item_count, status (completed or refunded), refund_usd |
| `data/synthetic/ad_spend.csv` | date, channel, source, medium, campaign, impressions, clicks, spend_usd |
| `data/synthetic/segment_identifies.jsonl` | Segment `identify` calls: type, messageId, timestamp, anonymousId, userId, traits (email, emailSha256, firstName, lastName, country, createdAt), context |
| `data/synthetic/segment_tracks.jsonl` | Segment `track` calls: type, event, messageId, timestamp, userId, properties, context |
| `data/synthetic/ground_truth/ground_truth_identity_links.csv` | customer_id, user_pseudo_id, device_role (primary or second), has_purchase, identify_emitted |

## Assumptions (all in `src/synthetic/config.py`)

| Assumption | Value | Why it matters |
|---|---|---|
| Buyers who check out as guests (not in CRM) | 12% | Some real buyers can never be matched to a customer |
| Non-buyers who register | 1% | Customers with no orders; low RFM |
| Customers whose account predates the GA4 window | 20% of buyers | Some customers are returning, not new |
| Customers with a second device | 8% | Tests cross-device matching |
| Segment `identify` captured on the main device | 85% | 15% of links have no identify event |
| `identify` captured on a second device | 70% | Second devices are harder to link |
| CRM web orders that carry the GA4 transaction ID | 92% | A second matching signal for buyers |
| App orders per customer (average) | 0.20 | Revenue GA4 web cannot attribute |
| Orders refunded in full | 3% | Revenue and CLV should use completed orders |
| Marketing opt-in | 55% | Customer attribute |
| Clicks per session | 1.00 to 1.15 | Some paid clicks never become a session |
| Paid cost per click | Paid Search 0.55 to 1.25 USD, Display 0.15 to 0.45, Paid Social 0.30 to 0.80, Affiliate (commission) 0.10 to 0.30, Email (platform cost) 0.02 to 0.08 | Sets spend; one value per campaign plus 10% daily noise |
| Click-through rate | Paid Search 2 to 5%, Display 0.3 to 0.8%, Paid Social 0.8 to 2%, Affiliate 1 to 3%, Email 2 to 6% | Sets impressions |

Order value and time for web orders are real. App order values are drawn from the real web order values (x 0.7 to 1.3).

## Rules for using it honestly

1. **Ground truth is for scoring only.** Models and dbt staging must never read `ground_truth/`. It is used in tests to measure identity-resolution precision and recall.
2. **Best possible accuracy is below 100%.** Guest buyers, the 15% uncaptured identify events, and uncaptured second devices cannot be matched by any method. The accuracy report must say so.
3. **Ad spend is an assumption.** It is sized from real paid sessions with assumed costs per click, so ROI and CPA show the method, not a real advertiser's results.
4. **Channels come from session-level parameters.** GA4's `traffic_source` field is user-level (first acquisition), so sessions use the `source`, `medium` and `campaign` event parameters instead. About 1 in 4 sessions has none of them; these are "Unassigned" and are never guessed. Campaign names in the sample are obfuscated (`<Other>`), so budget comparisons are mostly at channel level. Only `google / cpc` is real paid media; Affiliate, Email and Display are small.
5. Segment is mimicked, not used as a live service. The events follow Segment's `identify` and `track` format.
6. Customer names, emails and phone numbers are fake and cannot belong to real people.
