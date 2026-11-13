-- Every CRM customer has exactly one segment, buyers and non-buyers land where they should, and the money
-- in the segments adds up to the money in the profile.
with profile as (
    select count(*) as customers, countif(is_buyer) as buyers, sum(net_revenue_usd) as net from {{ ref('dim_customers') }}
),
seg as (
    select count(*) as customers, countif(is_buyer) as buyers, sum(historical_net_revenue_usd) as net,
           countif(segment = 'No Purchase Yet' and is_buyer) as buyers_without_segment,
           countif(segment != 'No Purchase Yet' and not is_buyer) as non_buyers_with_segment,
           countif(segment_order is null) as undefined_segments
    from {{ ref('fct_customer_segments') }}
)
select profile.customers as customers_profile, seg.customers as customers_segments
from profile, seg
where profile.customers != seg.customers or profile.buyers != seg.buyers or abs(profile.net - seg.net) > 0.01
   or seg.buyers_without_segment > 0 or seg.non_buyers_with_segment > 0 or seg.undefined_segments > 0
