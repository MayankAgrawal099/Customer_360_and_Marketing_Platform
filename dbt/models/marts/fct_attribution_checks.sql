-- The attribution sanity checks as a table: one row per check (and per model where it applies), with what was
-- expected, what was found and whether it passed. A test fails the build if any row fails, and the table
-- is the recorded evidence that credit adds up under every model.
--
--   credited orders / revenue      what each model credits equals the real orders and net revenue (fct_orders)
--   one unit per order             every order has credit totalling 1 per model, and no credit row is outside (0, 1]
--   one row per order              first and last touch hold exactly one row per order
--   channel table                  fct_attribution_by_channel adds up to the same orders and revenue
--   same under every model         orders without a known source are credited identically by all four models
--   orders mart = customer profile the revenue of the orders equals the revenue of the customer profile

with orders as (

    select count(*) as orders, sum(net_revenue_usd) as revenue from {{ ref('fct_orders') }}

),

profile as (

    select sum(net_revenue_usd) as revenue from {{ ref('dim_customers') }}

),

credits as (

    select
        model,
        count(*) as credit_rows,
        sum(credit) as credit,
        sum(credited_revenue_usd) as revenue,
        countif(credit <= 0 or credit > 1.000001) as bad_credit_rows
    from {{ ref('fct_attribution_credits') }}
    group by model

),

order_totals as (

    select conversion_id, model, sum(credit) as total
    from {{ ref('fct_attribution_credits') }}
    group by conversion_id, model

),

not_one as (

    select model, countif(abs(total - 1) > 0.0001) as orders_not_one
    from order_totals
    group by model

),

channel_totals as (

    select model, sum(attributed_orders) as orders, sum(attributed_revenue_usd) as revenue
    from {{ ref('fct_attribution_by_channel') }}
    group by model

),

no_source as (

    select
        credited_channel,
        max(attributed_revenue_usd) - min(attributed_revenue_usd) as spread,
        count(*) as models
    from {{ ref('fct_attribution_by_channel') }}
    where credited_channel in ('Direct / Unknown', 'No Touchpoint')
    group by credited_channel

),

checks as (

    select 'credited_orders_equal_orders' as check_name, c.model, o.orders as expected, c.credit as actual, 0.01 as tolerance
    from credits as c cross join orders as o

    union all
    select 'credited_revenue_equals_net_revenue', c.model, o.revenue, c.revenue, 0.01
    from credits as c cross join orders as o

    union all
    select 'every_order_has_one_unit_of_credit', model, 0, orders_not_one, 0
    from not_one

    union all
    select 'no_credit_row_outside_0_and_1', model, 0, bad_credit_rows, 0
    from credits

    union all
    select 'first_and_last_touch_have_one_row_per_order', c.model, o.orders, c.credit_rows, 0
    from credits as c cross join orders as o
    where c.model in ('first_touch', 'last_touch')

    union all
    select 'channel_table_orders_equal_orders', c.model, o.orders, c.orders, 0.01
    from channel_totals as c cross join orders as o

    union all
    select 'channel_table_revenue_equals_net_revenue', c.model, o.revenue, c.revenue, 0.01
    from channel_totals as c cross join orders as o

    union all
    select concat('same_revenue_under_all_models: ', credited_channel), 'all', 0, spread, 0.01
    from no_source

    union all
    select 'four_models_present', 'all', 4, count(distinct model), 0
    from credits

    union all
    select 'orders_revenue_equals_customer_profile', 'all', p.revenue, o.revenue, 0.01
    from orders as o cross join profile as p

)

select
    check_name,
    model,
    cast(expected as float64) as expected,
    cast(actual as float64) as actual,
    cast(actual as float64) - cast(expected as float64) as difference,
    tolerance,
    abs(cast(actual as float64) - cast(expected as float64)) <= tolerance as passed
from checks
