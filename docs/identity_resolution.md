# Identity resolution: rules

Goal: decide which website visitors (GA4 devices) are which CRM customers, so sessions can be tied to customers, orders and revenue. The accuracy numbers are in [`reports/identity_resolution_report.md`](../reports/identity_resolution_report.md), produced by `uv run python -m src.identity.run`.

## The problem

GA4 identifies a visitor only by `user_pseudo_id`, an anonymous id for one browser or device. The sample's `user_id` column is empty for every device, so GA4 cannot say who anyone is. A customer can also own several devices, and a visitor can buy as a guest and never appear in the CRM. Identity resolution connects the two worlds.

## Signals

| Signal | Where it lives | What it tells us |
|---|---|---|
| Segment `identify` event | `raw.segment_identifies` | `anonymousId` (the GA4 device) belongs to `userId` (the CRM `customer_id`), usually with the customer's hashed email. |
| Hashed email | `traits.emailSha256` in the identify event, `crm_customers.email_sha256` | A second, independent way to name the customer. Used to verify the `userId` and as a fallback. |
| CRM order with a GA4 transaction id | `crm_orders.ga_transaction_id` and the GA4 `purchase` event | The device that fired the purchase belongs to the order's customer. |

GA4 `user_id` plays no part because it is empty. The CRM `customer_id` takes its role and reaches GA4 through Segment's `userId`.

## Rules

Each piece of evidence produces a candidate (device, customer) link with a score. The scores are the evidence strength: 3 for two independent checks agreeing, 2 for a single signal.

| Rule | Score | Applies when |
|---|---|---|
| `identify_verified` | 3 | An identify event whose `userId` is a customer **and** whose email hash equals that customer's hash. |
| `order_match` | 3 | A CRM order's `ga_transaction_id` equals the `transaction_id` of a valid GA4 purchase. The device that fired it is linked to the order's customer. |
| `identify_unverified` | 2 | An identify event with a valid `userId` but no email hash, or a hash that matches no customer. |
| `email_hash` | 2 | An identify event whose `userId` is not a customer, but whose email hash matches exactly one customer. |

### Rejections (evidence that is never used)

| Case | Reason code | Why |
|---|---|---|
| Identify event where `userId` and the email hash point to **different** customers | `hash_conflict` | The two signals disagree; neither can be trusted. |
| Identify event with an unknown `userId` and an unknown hash | `unknown_customer` | Nobody to link to. |
| Identify event without a device id | `no_device_id` | Nothing to link. |
| Order whose transaction is not among the valid GA4 purchases | `transaction_not_in_ga4` | No device to link. |
| Same transaction fired on several devices | `duplicate_transaction_later_device` | The earliest purchase event is taken as the original; later devices are not linked. |
| An email hash shared by two customers | (hash never used) | A hash that is not unique proves nothing. |

### Combining and conflicts

1. Evidence for the same (device, customer) pair is combined. The pair's score is the sum of its **distinct** rules, so two orders from one device do not count twice, but an identify event plus an order do. `link_rule` is the strongest rule and `evidence_rules` lists all of them.
2. If a device is claimed by more than one customer, it keeps the customer with the highest score. A tie goes to the customer with the earliest evidence, then to the lowest `customer_id`, so reruns always give the same answer. The losing claims are written to `identity_rejected` as `lost_conflict`, and the winner is marked `had_conflict`.
3. `confidence` is `high` when the strongest rule is `identify_verified` or `order_match`, otherwise `medium`.
4. A customer may own many devices. A device belongs to at most one customer.

### Stitching sessions

A session is a device plus its `ga_session_id`. A session inherits the customer of its device, including sessions before the identify event or purchase happened. The link states that the device belongs to the customer, not only from the moment it was proven. This is how the dbt sessions model joins `identity.identity_links`. The limit of this choice is a shared device: if two people used it, earlier sessions may be credited to the wrong person.

## What is deliberately not done

- **No guessing.** There is no matching on country, time of day, browsing pattern or "looks like the same person". Devices without evidence stay anonymous.
- **No guest linking.** A buyer who checks out as a guest has no CRM record, so their purchase stays unattributed to any customer. The report shows how much revenue this is.
- **No use of ground truth.** `ground_truth_identity_links` is read only by `src/identity/score.py`, after the links exist. A test confirms `rules.py` never refers to it.

## How accuracy is measured

The synthetic generator knows the true device-to-customer links. After resolution, `score.py` compares:

| Measure | Definition |
|---|---|
| Precision | Share of links made that are correct. |
| Recall | Share of true links found. |
| Best possible recall | Share of true links that have any usable signal (an identify event, or an order that carries the GA4 transaction id). The rest cannot be found by a deterministic rule. |
| Missed although a signal existed | Should be 0; anything else means a rule is wrong. |
| Session, revenue and customer coverage | How much of the traffic, purchase revenue and customer base ends up linked. |

## Limits to state when presenting

- The data is synthetic, so signals never contradict each other except where the tests inject conflicts. High precision here shows that the **rules are logically sound**, not that identity resolution would be this clean on real data, where shared devices, mistyped emails and reused ids exist. Hence the conflict and hash-mismatch rules.
- Recall is capped by design: the generator drops 15% of identify events on main devices and 30% on second devices, and some orders carry no transaction id.
- The rules are deterministic and explainable. A probabilistic (fuzzy) layer could raise recall but would trade away the guarantee that every link has stated evidence.
