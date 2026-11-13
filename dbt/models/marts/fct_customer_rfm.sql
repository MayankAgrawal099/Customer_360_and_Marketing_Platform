-- One row per BUYER (a customer with at least one order): recency, frequency and monetary value, each
-- scored 1 (worst) to 5 (best). Customers without orders have no RFM; dim_customers still lists them.
--
-- Definitions
--   as_of_date   the day after the latest order in the data, so the result never depends on today's date
--   recency      days from the customer's latest order to as_of_date (smaller is better)
--   frequency    number of orders
--   monetary     net revenue in USD (order value minus refunds)
--
-- Scores
--   r_score and m_score are quintiles: ceil(5 * share of buyers at or below this value). Customers with
--   the same value always get the same score, so a tie is never split across two scores.
--   f_score uses fixed bands, because three quarters of buyers placed exactly one order and quintiles
--   cannot separate them: 1, 2, 3, 4 orders score 1, 2, 3, 4 and 5 or more orders score 5.

with as_of as (

    select date_add(max(order_date), interval 1 day) as as_of_date
    from {{ ref('fct_orders') }}

),

buyers as (

    select
        c.customer_id,
        a.as_of_date,
        c.first_order_date,
        c.last_order_date,
        date_diff(a.as_of_date, c.last_order_date, day) as recency_days,
        c.orders as frequency,
        c.net_revenue_usd as monetary_usd
    from {{ ref('dim_customers') }} as c
    cross join as_of as a
    where c.is_buyer

),

counted as (

    select
        *,
        count(*) over () as buyers,
        -- Buyers at or below this value (ties included): the larger the recency, the lower the rank.
        count(*) over (order by recency_days desc) as recency_rank,
        count(*) over (order by monetary_usd asc) as monetary_rank
    from buyers

),

scored as (

    select
        *,
        cast(ceil(5 * recency_rank / buyers) as int64) as r_score,
        least(frequency, 5) as f_score,
        cast(ceil(5 * monetary_rank / buyers) as int64) as m_score
    from counted

)

select
    customer_id,
    as_of_date,
    first_order_date,
    last_order_date,
    recency_days,
    frequency,
    monetary_usd,
    r_score,
    f_score,
    m_score,
    concat(cast(r_score as string), cast(f_score as string), cast(m_score as string)) as rfm_code,
    r_score + f_score + m_score as rfm_total
from scored
