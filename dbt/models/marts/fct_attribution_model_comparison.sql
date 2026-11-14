-- The four attribution models side by side: one row per credited channel, with the orders and net revenue each
-- model gives it, how far the models disagree, and whether the channel mostly introduces or closes customers.
-- Built only from fct_attribution_by_channel.
--
-- revenue_spread_usd   highest minus lowest revenue across the four models: how much the choice of model matters
-- introducing_gap_usd  first touch minus last touch revenue: positive = the channel is better at introducing
--                      customers than at closing them
-- role                 'Introduces' or 'Closes' when that gap is at least 5% of the channel's average revenue AND at
--                      least $25, otherwise 'Neutral'. Direct / Unknown and No Touchpoint are not channels: they
--                      collect orders whose journey has no known source, the same under every model.

with by_channel as (

    select * from {{ ref('fct_attribution_by_channel') }}

),

pivoted as (

    select
        credited_channel,
        sum(if(model = 'first_touch', attributed_orders, 0)) as orders_first_touch,
        sum(if(model = 'last_touch', attributed_orders, 0)) as orders_last_touch,
        sum(if(model = 'linear', attributed_orders, 0)) as orders_linear,
        sum(if(model = 'time_decay', attributed_orders, 0)) as orders_time_decay,
        sum(if(model = 'first_touch', attributed_revenue_usd, 0)) as revenue_first_touch,
        sum(if(model = 'last_touch', attributed_revenue_usd, 0)) as revenue_last_touch,
        sum(if(model = 'linear', attributed_revenue_usd, 0)) as revenue_linear,
        sum(if(model = 'time_decay', attributed_revenue_usd, 0)) as revenue_time_decay
    from by_channel
    group by credited_channel

),

totals as (

    select
        sum(revenue_first_touch) as total_first_touch,
        sum(revenue_last_touch) as total_last_touch,
        sum(revenue_linear) as total_linear,
        sum(revenue_time_decay) as total_time_decay
    from pivoted

),

measured as (

    select
        p.*,
        t.total_first_touch,
        t.total_last_touch,
        t.total_linear,
        t.total_time_decay,
        least(p.revenue_first_touch, p.revenue_last_touch, p.revenue_linear, p.revenue_time_decay) as revenue_min,
        greatest(p.revenue_first_touch, p.revenue_last_touch, p.revenue_linear, p.revenue_time_decay) as revenue_max,
        (p.revenue_first_touch + p.revenue_last_touch + p.revenue_linear + p.revenue_time_decay) / 4 as revenue_average,
        p.revenue_first_touch - p.revenue_last_touch as introducing_gap_usd
    from pivoted as p
    cross join totals as t

)

select
    credited_channel,
    credited_channel not in ('Direct / Unknown', 'No Touchpoint') as is_known_source,
    credited_channel in ('Paid Search', 'Display', 'Paid Social', 'Affiliate', 'Email') as is_paid_channel,
    orders_first_touch,
    orders_last_touch,
    orders_linear,
    orders_time_decay,
    revenue_first_touch,
    revenue_last_touch,
    revenue_linear,
    revenue_time_decay,
    safe_divide(revenue_first_touch, total_first_touch) as share_first_touch,
    safe_divide(revenue_last_touch, total_last_touch) as share_last_touch,
    safe_divide(revenue_linear, total_linear) as share_linear,
    safe_divide(revenue_time_decay, total_time_decay) as share_time_decay,
    revenue_min,
    revenue_max,
    revenue_max - revenue_min as revenue_spread_usd,
    safe_divide(revenue_max - revenue_min, revenue_average) as revenue_spread_pct,
    introducing_gap_usd,
    case
        when credited_channel in ('Direct / Unknown', 'No Touchpoint') then 'No known source'
        when abs(introducing_gap_usd) >= 25 and abs(introducing_gap_usd) >= 0.05 * revenue_average
            then if(introducing_gap_usd > 0, 'Introduces', 'Closes')
        else 'Neutral'
    end as role
from measured
