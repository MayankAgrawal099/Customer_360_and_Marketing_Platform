# Customer segments

Every CRM customer belongs to exactly one segment. The segments come from the RFM scores
(`marts.fct_customer_rfm`) and are built in `marts.fct_customer_segments`; the definitions below are stored
as a table in `marts.dim_customer_segments`, and tests keep the model, the table and this page in step.

## How the scores work

- **Recency score (R)**: 5 = ordered most recently, 1 = longest ago. Quintiles of buyers, so a score of 4-5 is the
  most recent 40% of buyers. In the current data that is roughly the last 5 weeks (days since last order up to
  about 38); score 1 is about 9 to 12 weeks ago. The exact day ranges move when the data changes.
- **Frequency score (F)**: 1, 2, 3, 4 orders score 1-4; 5 or more orders score 5. Three quarters of buyers ordered
  once, so frequency separates one-time buyers from repeat buyers more than it ranks them.
- **Monetary score (M)**: 5 = highest net revenue (order value minus refunds). Quintiles of buyers.

## Rules

The rules are checked from the top (order 1) down; the first rule that matches wins. Every combination of
scores matches exactly one rule, so nobody is left out and nobody is counted twice.

| Order | Segment | In plain words | Rule | What to do |
|---|---|---|---|---|
| 1 | **Champions** | Bought recently and often. | recency score 4-5 and 3 or more orders | Reward them, ask for reviews, offer early access. Do not discount. |
| 2 | **Loyal** | Repeat buyers who are still active. | 2 or more orders and recency score 3-5 (and not a Champion) | Cross-sell and loyalty offers to grow the basket. |
| 3 | **At Risk** | Repeat buyers who have gone quiet. | 2 or more orders and recency score 1-2 | Win-back campaign with a personal message. Best return on effort: they have shown they will buy again. |
| 4 | **Big Spenders** | One order, recent enough, and in the top 40% of spend. | 1 order, recency score 3-5 and monetary score 4-5 | Invite a second purchase with related premium products. |
| 5 | **New Customers** | One very recent order of ordinary size. | 1 order, recency score 4-5 and monetary score 1-3 | Welcome series and a nudge towards the second order. |
| 6 | **Promising** | One order, mid recency, ordinary size. | 1 order, recency score 3 and monetary score 1-3 | Time-limited offer to bring them back before they drift. |
| 7 | **Needs Attention** | One order, now getting old. | 1 order and recency score 2 | Reminder with best sellers before they lapse. |
| 8 | **Lost** | One order, the oldest in the data. | 1 order and recency score 1 | Low-cost reactivation only; keep out of paid campaigns. |
| 9 | **No Purchase Yet** | A customer account with no order. | no orders (not scored by RFM) | First-order incentive. Check marketing_opt_in before contacting. |

## Reading the segments

- **Value to protect:** Champions and Loyal. Repeat buyers are a small share of customers but a large share of revenue.
- **Value to win back:** At Risk. Repeat buyers who stopped ordering are the best win-back target.
- **Growth from one-time buyers:** Big Spenders, New Customers and Promising are one-order customers; the job is the
  second order, which is what turns a one-time buyer into a repeat buyer.
- **Do not chase:** Lost customers are the oldest one-order buyers; reactivate them cheaply or leave them.
- **No Purchase Yet** customers have no RFM, so they are never ranked against buyers. Check `marketing_opt_in` before
  contacting any customer.
- Segments describe the data as of the last order in the dataset (about three months). They are a snapshot, not a
  history: rerunning dbt after new data moves customers between segments.
