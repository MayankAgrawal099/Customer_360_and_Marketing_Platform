-- The attribution tables have composite keys, which column-level unique tests cannot express.
select 'int_conversion_touchpoints' as model, concat(order_id, '|', session_key) as key_
from {{ ref('int_conversion_touchpoints') }} group by order_id, session_key having count(*) > 1
union all
select 'fct_attribution_credits', concat(conversion_id, '|', model)
from {{ ref('fct_attribution_credits') }} group by conversion_id, model having count(*) > 1
union all
select 'fct_attribution_by_channel', concat(model, '|', credited_channel)
from {{ ref('fct_attribution_by_channel') }} group by model, credited_channel having count(*) > 1
