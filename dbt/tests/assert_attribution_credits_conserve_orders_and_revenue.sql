-- Every order gets exactly one full unit of credit per model, and no revenue is added or lost: the credited revenue of
-- each model equals the net revenue of the orders mart. First and last touch have exactly one row per order.
with orders as (
    select count(*) as orders, sum(net_revenue_usd) as revenue from {{ ref('fct_orders') }}
),
per_model as (
    select model, count(*) as rows_, count(distinct conversion_id) as orders, sum(credit) as credit,
           sum(credited_revenue_usd) as revenue
    from {{ ref('fct_attribution_credits') }}
    group by model
),
per_order as (
    select conversion_id, model from {{ ref('fct_attribution_credits') }}
    group by conversion_id, model having abs(sum(credit) - 1) > 0.0001
)
select m.model, 'model total' as problem
from per_model as m, orders as o
where m.orders != o.orders or abs(m.credit - o.orders) > 0.01 or abs(m.revenue - o.revenue) > 0.01
   or (m.model in ('first_touch', 'last_touch') and m.rows_ != o.orders)
union all
select model, conversion_id from per_order
union all
select model, conversion_id from {{ ref('fct_attribution_credits') }} where credit <= 0 or credit > 1.000001
union all
select 'models', 'missing model' from (select count(distinct model) as n from {{ ref('fct_attribution_credits') }}) where n < 4
