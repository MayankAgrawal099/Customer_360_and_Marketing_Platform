-- Ad spend is built from GA4 sessions, so every spend day must fall inside the GA4 window.
select ad_spend_id, date
from {{ ref('stg_ad_spend') }}
where date not between date '2020-11-01' and date '2021-01-31'
