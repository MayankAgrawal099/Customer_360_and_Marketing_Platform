-- Every linked device must be a real GA4 device.
select l.user_pseudo_id
from {{ ref('stg_identity__links') }} l
left join (select distinct user_pseudo_id from {{ ref('stg_ga4__events') }}) e using (user_pseudo_id)
where e.user_pseudo_id is null
