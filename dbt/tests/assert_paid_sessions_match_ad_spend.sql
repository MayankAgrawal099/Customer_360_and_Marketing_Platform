-- The synthetic ad spend was sized from real paid sessions: one row per campaign per day, with
-- clicks between 1.00 and 1.15 times the sessions. So every paid (day, campaign) in the sessions must have
-- a spend row and the reverse, and the clicks must be in that range.
with paid as (
    select session_date as date, ad_campaign_key as campaign_key, count(*) as sessions
    from {{ ref('fct_sessions') }}
    where is_paid
    group by session_date, ad_campaign_key
),
spend as (
    select date, campaign_key, clicks from {{ ref('stg_ad_spend') }}
)
select coalesce(paid.date, spend.date) as date, coalesce(paid.campaign_key, spend.campaign_key) as campaign_key,
       paid.sessions, spend.clicks
from paid
full outer join spend on spend.date = paid.date and spend.campaign_key = paid.campaign_key
where paid.sessions is null
   or spend.clicks is null
   or spend.clicks < paid.sessions
   or spend.clicks > paid.sessions * 1.15 + 0.5
