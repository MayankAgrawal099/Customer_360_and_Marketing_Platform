-- Campaign ROI must tie to its inputs: all the ad spend is in it under every model, all the campaign-tagged revenue
-- the models credit is in it (none lost because a campaign has no spend row), the GA4 benchmark equals the paid
-- sessions' purchases, and the channel table equals the campaign table.
with models as (
    select 'first_touch' as model union all select 'last_touch' union all select 'linear' union all select 'time_decay'
),
spend as (select sum(spend_usd) as spend, sum(clicks) as clicks, count(distinct campaign_key) as campaigns from {{ ref('stg_ad_spend') }}),
credited as (
    select model, sum(credit) as orders, sum(credited_revenue_usd) as revenue
    from {{ ref('fct_attribution_credits') }} where ad_campaign_key is not null group by model
),
sessions as (
    select sum(valid_purchases) as orders, sum(revenue_usd) as revenue from {{ ref('fct_sessions') }} where is_paid
),
campaign as (
    select model, count(*) as campaigns, sum(spend_usd) as spend, sum(clicks) as clicks, sum(attributed_orders) as orders,
           sum(attributed_revenue_usd) as revenue
    from {{ ref('fct_campaign_roi') }} group by model
),
channel as (
    select model, sum(spend_usd) as spend, sum(attributed_orders) as orders, sum(attributed_revenue_usd) as revenue
    from {{ ref('fct_channel_roi') }} group by model
),
comparisons as (
    select 'spend is all in the campaign table' as problem, c.model, s.spend as expected, c.spend as actual
    from campaign as c cross join spend as s
    union all
    select 'clicks are all in the campaign table', c.model, s.clicks, c.clicks from campaign as c cross join spend as s
    union all
    select 'one row per campaign', c.model, s.campaigns, c.campaigns from campaign as c cross join spend as s
    union all
    select 'credited orders are all in the campaign table', c.model, d.orders, c.orders
    from campaign as c inner join credited as d on d.model = c.model
    union all
    select 'credited revenue is all in the campaign table', c.model, d.revenue, c.revenue
    from campaign as c inner join credited as d on d.model = c.model
    union all
    select 'ga4_session orders equal paid sessions purchases', c.model, x.orders, c.orders
    from campaign as c cross join sessions as x where c.model = 'ga4_session'
    union all
    select 'ga4_session revenue equals paid sessions revenue', c.model, x.revenue, c.revenue
    from campaign as c cross join sessions as x where c.model = 'ga4_session'
    union all
    select 'channel table spend equals campaign table', h.model, c.spend, h.spend
    from campaign as c inner join channel as h on h.model = c.model
    union all
    select 'channel table orders equal campaign table', h.model, c.orders, h.orders
    from campaign as c inner join channel as h on h.model = c.model
    union all
    select 'channel table revenue equals campaign table', h.model, c.revenue, h.revenue
    from campaign as c inner join channel as h on h.model = c.model
    union all
    select 'five models present', 'all', 5, count(distinct model) from campaign
)
select problem, model, expected, actual from comparisons where abs(expected - actual) > 0.01
