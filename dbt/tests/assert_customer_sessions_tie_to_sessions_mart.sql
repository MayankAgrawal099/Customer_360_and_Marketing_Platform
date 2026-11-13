-- Sessions on linked devices: the profile must count exactly the identified sessions of the sessions mart.
with mart as (
    select count(*) as sessions, countif(is_converted) as converted
    from {{ ref('fct_sessions') }} where customer_id is not null
),
profile as (
    select sum(sessions) as sessions, sum(converted_sessions) as converted from {{ ref('dim_customers') }}
),
links as (
    select count(*) as devices from {{ ref('stg_identity__links') }}
),
profile_devices as (
    select sum(linked_devices) as devices from {{ ref('dim_customers') }}
)
select mart.sessions as sessions_mart, profile.sessions as sessions_profile
from mart, profile, links, profile_devices
where mart.sessions != profile.sessions
   or mart.converted != profile.converted
   or links.devices != profile_devices.devices
