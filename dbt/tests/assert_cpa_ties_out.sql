-- The CPA tables must agree with the ROI tables they are built on, with the order data, and with themselves:
-- same rows, spend, orders and revenue; CPA recomputed from spend and orders; new customers never exceed orders and equal the
-- credited first orders; the channel table equals the campaign table.
with campaign as (select * from {{ ref('fct_campaign_cpa') }}),
roi as (select * from {{ ref('fct_campaign_roi') }}),
channel as (select * from {{ ref('fct_channel_cpa') }}),
first_orders as (
    select c.model, sum(c.credit) as new_customers
    from {{ ref('fct_attribution_credits') }} as c
    inner join {{ ref('fct_orders') }} as o on o.order_id = c.conversion_id
    where c.ad_campaign_key is not null and o.is_first_order
    group by c.model
),
campaign_totals as (
    select model, count(*) as campaigns, sum(spend_usd) as spend, sum(attributed_orders) as orders,
           sum(attributed_revenue_usd) as revenue, sum(new_customers) as new_customers
    from campaign group by model
),
roi_totals as (
    select model, count(*) as campaigns, sum(spend_usd) as spend, sum(attributed_orders) as orders,
           sum(attributed_revenue_usd) as revenue
    from roi group by model
),
channel_totals as (
    select model, sum(spend_usd) as spend, sum(attributed_orders) as orders, sum(new_customers) as new_customers
    from channel group by model
),
comparisons as (
    select 'campaign rows equal roi rows' as problem, c.model, r.campaigns as expected, c.campaigns as actual
    from campaign_totals as c inner join roi_totals as r on r.model = c.model
    union all
    select 'spend equals roi spend', c.model, r.spend, c.spend from campaign_totals as c inner join roi_totals as r on r.model = c.model
    union all
    select 'orders equal roi orders', c.model, r.orders, c.orders from campaign_totals as c inner join roi_totals as r on r.model = c.model
    union all
    select 'revenue equals roi revenue', c.model, r.revenue, c.revenue from campaign_totals as c inner join roi_totals as r on r.model = c.model
    union all
    select 'new customers equal credited first orders', c.model, f.new_customers, c.new_customers
    from campaign_totals as c inner join first_orders as f on f.model = c.model
    union all
    select 'channel spend equals campaign spend', h.model, c.spend, h.spend
    from campaign_totals as c inner join channel_totals as h on h.model = c.model
    union all
    select 'channel orders equal campaign orders', h.model, c.orders, h.orders
    from campaign_totals as c inner join channel_totals as h on h.model = c.model
    union all
    select 'channel new customers equal campaign new customers', h.model, c.new_customers, h.new_customers
    from campaign_totals as c inner join channel_totals as h on h.model = c.model
    union all
    select 'cpa is spend over orders', model, spend_usd / attributed_orders, cpa_usd
    from campaign where attributed_orders > 0
    union all
    select 'new customers never exceed orders', model, attributed_orders, new_customers
    from campaign where new_customers > attributed_orders + 0.000001
    union all
    select 'ga4_session has no new customers', model, 0, 1 from campaign where model = 'ga4_session' and new_customers is not null
)
select problem, model, expected, actual from comparisons where abs(expected - actual) > 0.01
