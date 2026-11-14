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
| **Linear** | the credit split **equally** over all touchpoints with a known source: every visit counts the same |
| **Time decay** | the credit split with **more for recent visits**: a touchpoint's weight halves for every 7 days (the half-life) it lies before the order, and the shares are the weights divided by their total |

Time-decay weight = 0.5 ^ (days before the order / 7). A visit on the day of the order has weight 1, one a week
earlier 0.5, two weeks earlier 0.25. The 7-day half-life is a convention, chosen because the look-back is 30 days;
it is a single number (`half_life_days`) in `fct_attribution_credits.sql`.

When a journey has no known source, first touch takes the earliest touchpoint and last touch the latest one, while
linear and time decay share the credit over all of its touchpoints; whichever is used, the credit is labelled
Direct / Unknown. An order with no touchpoint at all keeps its one full unit of credit under every model, labelled
No Touchpoint.

Every model gives each order **exactly 1 unit of credit in total**, so orders and revenue add up to the same totals under
all four, and the models can be put side by side in `fct_attribution_by_channel`. First and last touch have one row per
order in `fct_attribution_credits`; linear and time decay have one row per credited touchpoint, so credited orders in
the channel table can be fractions (for example 0.5 of an order).

## Comparing the models

`marts.fct_attribution_model_comparison` puts the four models side by side, one row per channel: orders and net revenue
under each model, each model's share of revenue, the **spread** (highest minus lowest revenue across the models: how much
the choice of model matters for that channel), and a **role**. The role compares first and last touch: **Introduces**
when first touch gives the channel at least 5% (and at least $25) more than last touch, **Closes** when it gives less,
**Neutral** otherwise. Direct / Unknown and No Touchpoint are labelled *No known source*.

`marts.fct_attribution_checks` records the sanity checks as a table, and a dbt test fails the build if any check fails:

| Check | What it proves |
|---|---|
| credited orders equal orders | each model credits exactly the real number of orders |
| credited revenue equals net revenue | each model credits exactly the real net revenue |
| one unit of credit per order | every order's credit adds up to 1 under every model; no credit is outside 0 to 1 |
| first and last touch: one row per order | those two models hold exactly one row for each order |
| channel table orders / revenue | the by-channel table adds up to the same orders and revenue |
| same revenue under all models | orders without a known source are credited identically by all four models |
| orders equal customer profile | the orders' net revenue equals the customer profile's |
| four models present | no model is missing |

`uv run python -m src.attribution_report` turns both tables into `reports/attribution_comparison.md`, with every figure in
the text computed from the tables.

## Reading the results

- First touch rewards channels that **introduce** customers (search, social, display); last touch rewards channels that
  **close** them (email, branded search). A channel scoring much higher on one than the other plays that role.
- An order with a single known-source touchpoint gets the same credit under all four models. `fct_attribution_journeys`
  (`first_and_last_differ`) shows how many orders first and last touch disagree on; all four models differ only on customers
  with several visits.
- Only a minority of GA4 sessions sit on customers' linked devices, so many orders have a short journey.
- Orders with No Touchpoint cannot be credited to any channel. Do not drop them when reporting channel revenue.
- Linear is the fairest view of a long journey, time decay the one that favours the channels that closed it. If a channel
  scores about the same under all four models, its credit does not depend on the choice of model; a channel that moves a
  lot is one whose role (introducing versus closing) matters for the budget decision.
