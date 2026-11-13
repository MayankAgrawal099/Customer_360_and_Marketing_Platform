-- A touchpoint is a session of the purchasing device or of a device linked to the order's customer, inside the
-- 30 days before the order (the purchasing session is always allowed), and each (order, session) appears once.
with t as (
    select * from {{ ref('int_conversion_touchpoints') }}
),
o as (
    select order_id, customer_id, order_ts, ga_user_pseudo_id, ga_session_key from {{ ref('fct_orders') }}
),
links as (
    select user_pseudo_id, customer_id from {{ ref('stg_identity__links') }}
)
select t.order_id, t.session_key, 'not on a device of this order' as problem
from t
inner join o on o.order_id = t.order_id
left join links as l on l.user_pseudo_id = t.user_pseudo_id and l.customer_id = o.customer_id
where t.user_pseudo_id != coalesce(o.ga_user_pseudo_id, '') and l.user_pseudo_id is null
union all
select t.order_id, t.session_key, 'outside the lookback window'
from t
inner join o on o.order_id = t.order_id
where t.session_key != coalesce(o.ga_session_key, '')
  and (t.session_start_ts > o.order_ts or t.days_before_order > 30)
union all
select order_id, session_key, 'appears more than once'
from t group by order_id, session_key having count(*) > 1
union all
select o.order_id, o.ga_session_key, 'purchase session missing from its own journey'
from o
left join t on t.order_id = o.order_id and t.session_key = o.ga_session_key
where o.ga_session_key is not null and t.session_key is null
