-- RFM has one row for every buyer and none for customers without orders, and carries their real totals.
with profile as (
    select countif(is_buyer) as buyers, sum(if(is_buyer, orders, 0)) as orders, sum(if(is_buyer, net_revenue_usd, 0)) as net
    from {{ ref('dim_customers') }}
),
rfm as (
    select count(*) as buyers, sum(frequency) as orders, sum(monetary_usd) as net, count(distinct as_of_date) as as_of_dates
    from {{ ref('fct_customer_rfm') }}
),
strangers as (
    select count(*) as n from {{ ref('fct_customer_rfm') }} as r
    join {{ ref('dim_customers') }} as c on c.customer_id = r.customer_id where not c.is_buyer
)
select profile.buyers as buyers_profile, rfm.buyers as buyers_rfm
from profile, rfm, strangers
where profile.buyers != rfm.buyers or profile.orders != rfm.orders or abs(profile.net - rfm.net) > 0.01
   or strangers.n > 0 or rfm.as_of_dates != 1
