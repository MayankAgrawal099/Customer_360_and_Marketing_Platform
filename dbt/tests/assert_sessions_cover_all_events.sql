-- No session may be lost or invented: the sessions table must have exactly the sessions found in the events.
with expected as (
    select count(distinct session_key) as n from {{ ref('stg_ga4__events') }} where ga_session_id is not null
),
actual as (
    select count(*) as n from {{ ref('fct_sessions') }}
)
select expected.n as expected_sessions, actual.n as actual_sessions
from expected, actual
where expected.n != actual.n
