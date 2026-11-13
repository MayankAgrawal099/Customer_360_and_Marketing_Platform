-- Re-checks first and last touch against the touchpoints themselves, written a second way:
--   known_source      the credited session exists in the journey, has a known source, carries the credited channel, and
--                     no known-source touchpoint is earlier (first_touch) or later (last_touch)
--   direct_or_unknown the journey has touchpoints but none with a known source
--   no_touchpoint     the journey has no touchpoints at all
with credits as (
    select * from {{ ref('fct_attribution_credits') }}
),
touchpoints as (
    select * from {{ ref('int_conversion_touchpoints') }}
)
select c.conversion_id, c.model, 'credited session is not a known-source touchpoint of the order' as problem
from credits as c
left join touchpoints as t on t.order_id = c.conversion_id and t.session_key = c.touchpoint_session_key
where c.attribution_basis = 'known_source'
  and (t.session_key is null or not t.has_source or t.channel_group != c.credited_channel)
union all
select c.conversion_id, c.model, 'a better known-source touchpoint exists'
from credits as c
inner join touchpoints as t on t.order_id = c.conversion_id and t.session_key = c.touchpoint_session_key
inner join touchpoints as o on o.order_id = c.conversion_id and o.has_source
where c.attribution_basis = 'known_source'
  and ((c.model = 'first_touch' and o.session_start_ts < t.session_start_ts)
    or (c.model = 'last_touch' and o.session_start_ts > t.session_start_ts))
union all
select c.conversion_id, c.model, 'fallback although a known source exists'
from credits as c
inner join touchpoints as t on t.order_id = c.conversion_id and t.has_source
where c.attribution_basis != 'known_source'
union all
select c.conversion_id, c.model, 'no_touchpoint although touchpoints exist'
from credits as c
inner join touchpoints as t on t.order_id = c.conversion_id
where c.attribution_basis = 'no_touchpoint'
union all
select conversion_id, model, 'basis, channel and session disagree'
from credits
where (attribution_basis = 'no_touchpoint') != (touchpoint_session_key is null)
   or (attribution_basis = 'no_touchpoint') != (credited_channel = 'No Touchpoint')
   or (attribution_basis = 'direct_or_unknown') != (credited_channel = 'Direct / Unknown')
   or (attribution_basis = 'known_source' and credited_channel in ('Self Referral', 'Direct', 'Unassigned', 'Other'))
