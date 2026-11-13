-- CLV has one row per buyer, its historical value is the real net revenue, and nothing is negative.
with profile as (
    select countif(is_buyer) as buyers, sum(if(is_buyer, net_revenue_usd, 0)) as net, sum(if(is_buyer, orders, 0)) as orders
    from {{ ref('dim_customers') }}
),
clv as (
    select count(*) as buyers, sum(historical_net_revenue_usd) as net, sum(orders) as orders,
           countif(predicted_orders_90d < 0 or predicted_revenue_90d_usd < 0 or predicted_revenue_12m_usd < 0
                   or expected_aov_usd < 0 or clv_12m_usd < historical_net_revenue_usd - 0.005) as bad_rows
    from {{ ref('fct_customer_clv') }}
)
select profile.buyers as buyers_profile, clv.buyers as buyers_clv
from profile, clv
where profile.buyers != clv.buyers or profile.orders != clv.orders or abs(profile.net - clv.net) > 0.01 or clv.bad_rows > 0
