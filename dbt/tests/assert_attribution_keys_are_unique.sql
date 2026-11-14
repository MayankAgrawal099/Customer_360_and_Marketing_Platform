-- The attribution tables have composite keys, which column-level unique tests cannot express.
select 'int_conversion_touchpoints' as model, concat(order_id, '|', session_key) as key_
from {{ ref('int_conversion_touchpoints') }} group by order_id, session_key having count(*) > 1
union all
select 'fct_attribution_credits', concat(conversion_id, '|', model, '|', coalesce(touchpoint_session_key, ''))
from {{ ref('fct_attribution_credits') }} group by conversion_id, model, touchpoint_session_key having count(*) > 1
union all
select 'fct_attribution_by_channel', concat(model, '|', credited_channel)
from {{ ref('fct_attribution_by_channel') }} group by model, credited_channel having count(*) > 1
union all
select 'fct_attribution_checks', concat(check_name, '|', model)
from {{ ref('fct_attribution_checks') }} group by check_name, model having count(*) > 1
union all
select 'fct_campaign_roi', concat(model, '|', campaign_key)
from {{ ref('fct_campaign_roi') }} group by model, campaign_key having count(*) > 1
union all
select 'fct_channel_roi', concat(model, '|', channel)
from {{ ref('fct_channel_roi') }} group by model, channel having count(*) > 1
union all
select 'fct_campaign_cpa', concat(model, '|', campaign_key)
from {{ ref('fct_campaign_cpa') }} group by model, campaign_key having count(*) > 1
union all
select 'fct_channel_cpa', concat(model, '|', channel)
from {{ ref('fct_channel_cpa') }} group by model, channel having count(*) > 1
