-- Each customer's orders are numbered 1, 2, 3... in time order, and the gaps between orders add up.
with per_customer as (
    select customer_id, count(*) as orders, max(order_number) as last_number, count(distinct order_number) as numbers
    from {{ ref('fct_orders') }}
    group by customer_id
)
select customer_id from per_customer where last_number != orders or numbers != orders
union all
select order_id from {{ ref('fct_orders') }}
where is_first_order != (previous_order_ts is null)
   or (is_first_order and (days_since_previous_order is not null or days_since_first_order != 0))
   or (not is_first_order and (days_since_previous_order < 0 or days_since_first_order < days_since_previous_order))
