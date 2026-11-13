-- One row per BUYER: what the customer has already brought in (historical value) and what they are
-- expected to bring in over the next 90 days and the next 12 months (predicted value).
--
-- Method (kept deliberately simple so it can be explained and checked)
--   1. Everything is measured to the same as_of_date as the RFM model.
--   2. Repeat rate: a customer's repeat orders (orders after the first) per day since the first order.
--      The data covers only about three months, so one customer's own rate is noisy. Each rate is
--      therefore pulled towards the rate of ALL buyers, as a Gamma-Poisson posterior mean:
--          rate = (own repeat orders + prior_days * population rate) / (own days observed + prior_days)
--      With prior_days = 90 a customer needs roughly three months of history before their own
--      behaviour outweighs the population's.
--   3. Order value: the same pull towards the population's average order value, with prior_orders = 3:
--          aov  = (own net revenue + prior_orders * population aov) / (own orders + prior_orders)
--   4. predicted revenue = rate * horizon_days * aov, for 90 and 365 days. Value is NET revenue (after refunds).
--   5. clv_12m_usd = historical net revenue + predicted revenue for the next 12 months.
--
-- Read the 12-month figure with care: 365 days is about four times the history observed, and the
-- model does not let customers churn. The 90-day figure sits within what the data has actually seen.
-- Customers without orders are not valued here.

with params as (

    select
        90 as prior_days,
        3 as prior_orders,
        90 as short_horizon_days,
        365 as long_horizon_days

),

buyers as (

    select
        r.customer_id,
        r.as_of_date,
        c.first_order_date,
        c.last_order_date,
        c.orders,
        c.orders - 1 as repeat_orders,
        c.gross_revenue_usd,
        c.net_revenue_usd,
        date_diff(r.as_of_date, c.first_order_date, day) as days_observed
    from {{ ref('fct_customer_rfm') }} as r
    inner join {{ ref('dim_customers') }} as c on c.customer_id = r.customer_id

),

population as (

    select
        sum(repeat_orders) / sum(days_observed) as population_repeat_rate_per_day,
        sum(net_revenue_usd) / sum(orders) as population_aov_usd
    from buyers

),

rated as (

    select
        b.*,
        p.population_repeat_rate_per_day,
        p.population_aov_usd,
        (b.repeat_orders + k.prior_days * p.population_repeat_rate_per_day)
            / (b.days_observed + k.prior_days) as expected_repeat_rate_per_day,
        (b.net_revenue_usd + k.prior_orders * p.population_aov_usd)
            / (b.orders + k.prior_orders) as expected_aov_usd,
        k.short_horizon_days,
        k.long_horizon_days
    from buyers as b
    cross join population as p
    cross join params as k

)

select
    customer_id,
    as_of_date,
    first_order_date,
    last_order_date,
    days_observed,
    orders,
    repeat_orders,
    gross_revenue_usd,
    net_revenue_usd as historical_net_revenue_usd,
    population_repeat_rate_per_day,
    population_aov_usd,
    expected_repeat_rate_per_day,
    expected_aov_usd,
    expected_repeat_rate_per_day * short_horizon_days as predicted_orders_90d,
    expected_repeat_rate_per_day * short_horizon_days * expected_aov_usd as predicted_revenue_90d_usd,
    expected_repeat_rate_per_day * long_horizon_days as predicted_orders_12m,
    expected_repeat_rate_per_day * long_horizon_days * expected_aov_usd as predicted_revenue_12m_usd,
    net_revenue_usd + expected_repeat_rate_per_day * long_horizon_days * expected_aov_usd as clv_12m_usd
from rated
