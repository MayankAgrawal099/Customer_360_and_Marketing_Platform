-- One row per paid campaign per day. Synthetic spend: see docs/synthetic_data.md for the assumptions.
--
-- Some real GA4 sessions have a source and medium but no campaign parameter, so raw.ad_spend holds empty
-- source, medium or campaign values. They are set to '(not set)' here, so the ids and keys below are never
-- null (concat returns null if any part is null). The sessions model must use the same '(not set)' value
-- when it joins to this table.

with cleaned as (

    select
        date,
        channel,
        coalesce(nullif(trim(source), ''), '(not set)') as source,
        coalesce(nullif(trim(medium), ''), '(not set)') as medium,
        coalesce(nullif(trim(campaign), ''), '(not set)') as campaign,
        impressions,
        clicks,
        spend_usd
    from {{ source('raw', 'ad_spend') }}

)

select
    concat(cast(date as string), '|', channel, '|', source, '|', medium, '|', campaign) as ad_spend_id,
    concat(channel, '|', source, '|', medium, '|', campaign) as campaign_key,
    date,
    channel,
    source,
    medium,
    campaign,
    impressions,
    clicks,
    spend_usd,
    safe_divide(spend_usd, clicks) as cost_per_click,
    safe_divide(clicks, impressions) as click_through_rate
from cleaned
