# Attribution

Attribution answers one question: **which marketing channel should get the credit for an order?**
This page defines the journey, the credit rules and their limits. The tables are
`marts.fct_attribution_credits` (who gets the credit for each order, per model), `marts.fct_attribution_by_channel`
(credit by channel, per model) and `marts.fct_attribution_journeys` (one row per order, showing where the models disagree).
Their input is `intermediate.int_conversion_touchpoints`.

## What is attributed

Every CRM order (web and app, 5,120 in the current data) with its **net revenue** (order value minus refunds). Each
model gives each order exactly **1 unit of credit** in total, so credited orders and credited revenue add up to the real
totals under every model. A test fails the build if they do not. GA4 purchases by visitors who are not CRM customers are
not part of this table: attribution here follows customers.

## The journey of an order

An order's journey is every GA4 session (a "touchpoint") that:

1. is on the device that placed the order (matched web orders), or on any device identity resolution linked to the
   customer (`docs/identity_resolution.md`), and
2. started no later than the order and no more than **30 days** before it. A matched order's own purchasing session is
   always kept.

This is how app orders, and web orders without a transaction id, still get a journey: they borrow the customer's linked
devices. The data covers about three months, so the 30-day look-back cuts off older visits that a longer history would
keep.

## Which touchpoints can receive credit

A touchpoint **has a known source** unless its channel is one of four that say nothing about what brought the customer in:

| Channel | Known source? | Why |
|---|---|---|
| Paid Search, Display, Paid Social, Affiliate, Email | yes | marketing channels |
| Organic Search, Organic Social, Referral | yes | real sources |
| **Direct** | no | typed address or no referrer: the visit has no source |
| **Self Referral** | no | the visitor navigated back from the store's own domain: internal, not a source |
| **Unassigned** | no | GA4 recorded no source at all |
| **Other** | no | in this dataset only the values GA4 hides in its public sample (`<Other>`, `(data deleted)`, about 31,800 sessions): the real source exists but is not shown, so there is nothing to credit |

The models look past the four "no" channels to the touchpoints that do have a source (the idea behind GA4's default
"last non-direct click"). If the journey has none, the credit falls back so that no order is lost:

| `attribution_basis` | `credited_channel` | When |
|---|---|---|
| `known_source` | the touchpoint's channel | at least one touchpoint has a known source |
| `direct_or_unknown` | **Direct / Unknown** | the journey has touchpoints, but only Direct, Self Referral, Unassigned or Other ones |
| `no_touchpoint` | **No Touchpoint** | no session at all (the customer has no linked device, or no visit in the 30 days) |

Direct / Unknown and No Touchpoint are shown as their own rows, never hidden: they are the honest size of what
attribution cannot explain.

## The models

| Model | Credit rule |
|---|---|
| **First touch** | all credit to the **earliest** touchpoint with a known source: what brought the customer in |
| **Last touch** | all credit to the **latest** touchpoint with a known source before the order: what closed the sale |

When a journey has no known source, first touch takes the earliest touchpoint and last touch the latest one, and the
credit is labelled Direct / Unknown. Linear and time-decay models, which split credit across the journey, are added to
the same table later.

## Reading the results

- First touch rewards channels that **introduce** customers (search, social, display); last touch rewards channels that
  **close** them (email, branded search). A channel scoring much higher on one than the other plays that role.
- An order with a single known-source touchpoint gets the same credit under both models. `fct_attribution_journeys`
  (`first_and_last_differ`) shows how many orders the models disagree on; they differ only on customers with several
  visits.
- Only a minority of GA4 sessions sit on customers' linked devices, so many orders have a short journey.
- Orders with No Touchpoint cannot be credited to any channel. Do not drop them when reporting channel revenue.
