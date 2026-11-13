-- One row per CRM customer (all of them) with their segment, the scores behind it and their value.
-- Buyers are segmented from their RFM scores (fct_customer_rfm); customers without an order are
-- 'No Purchase Yet'. The rules are written once, in dim_customer_segments and docs/customer_segments.md,
-- and applied here top to bottom: the first matching rule wins, and every combination of scores matches one.

with customers as (

    select * from {{ ref('dim_customers') }}

),

rfm as (

    select * from {{ ref('fct_customer_rfm') }}

),

clv as (

    select
        customer_id,
        predicted_revenue_90d_usd,
        predicted_revenue_12m_usd,
        clv_12m_usd
    from {{ ref('fct_customer_clv') }}

),

assigned as (

    select
        c.customer_id,
        c.country,
        c.marketing_opt_in,
        c.is_buyer,
        c.has_linked_device,
        c.first_order_channel_group,
        c.first_session_channel_group,
        r.recency_days,
        coalesce(r.frequency, 0) as orders,
        coalesce(r.monetary_usd, 0) as historical_net_revenue_usd,
        r.r_score,
        r.f_score,
        r.m_score,
        r.rfm_code,
        r.rfm_total,
        coalesce(v.predicted_revenue_90d_usd, 0) as predicted_revenue_90d_usd,
        coalesce(v.predicted_revenue_12m_usd, 0) as predicted_revenue_12m_usd,
        coalesce(v.clv_12m_usd, 0) as clv_12m_usd,
        case
            when r.customer_id is null then 'No Purchase Yet'
            when r.r_score >= 4 and r.f_score >= 3 then 'Champions'
            when r.f_score >= 2 and r.r_score >= 3 then 'Loyal'
            when r.f_score >= 2 then 'At Risk'
            when r.r_score >= 3 and r.m_score >= 4 then 'Big Spenders'
            when r.r_score >= 4 then 'New Customers'
            when r.r_score = 3 then 'Promising'
            when r.r_score = 2 then 'Needs Attention'
            else 'Lost'
        end as segment
    from customers as c
    left join rfm as r on r.customer_id = c.customer_id
    left join clv as v on v.customer_id = c.customer_id

)

select
    a.customer_id,
    a.segment,
    d.segment_order,
    a.is_buyer,
    a.r_score,
    a.f_score,
    a.m_score,
    a.rfm_code,
    a.rfm_total,
    a.recency_days,
    a.orders,
    a.historical_net_revenue_usd,
    a.predicted_revenue_90d_usd,
    a.predicted_revenue_12m_usd,
    a.clv_12m_usd,
    a.country,
    a.marketing_opt_in,
    a.has_linked_device,
    a.first_order_channel_group,
    a.first_session_channel_group
from assigned as a
left join {{ ref('dim_customer_segments') }} as d on d.segment = a.segment
