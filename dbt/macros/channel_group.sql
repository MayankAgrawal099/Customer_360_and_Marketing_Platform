{#
  Marketing channel of a session, from its source and medium.

  Same rules, in the same order, as channel_group() in src/synthetic/channels.py, which sized the
  synthetic ad spend. tests/test_dbt_sessions.py runs both on the same inputs and fails if they differ.

  A session whose source is the store's own domain is 'Self Referral': GA4 restarts the session when a visitor
  moves between the main site and the shop, and that is not a marketing touch.

  A session with no source and no medium is 'Unassigned'. It is never guessed: the GA4 sample leaves the
  source parameters empty on about 1 session in 4.

  Usage:  {{ channel_group('source', 'medium') }}   (two column names or expressions)
#}
{% macro channel_group(source, medium) -%}
{%- set s = "lower(trim(coalesce(" ~ source ~ ", '')))" -%}
{%- set m = "lower(trim(coalesce(" ~ medium ~ ", '')))" -%}
case
    when {{ s }} = '' and {{ m }} = '' then 'Unassigned'
    when strpos({{ s }}, 'googlemerchandisestore.com') > 0 then 'Self Referral'
    when {{ m }} in ('cpc', 'ppc', 'paidsearch', 'paid search') then 'Paid Search'
    when {{ m }} in ('cpm', 'display', 'banner')
        or strpos({{ s }}, 'googleads.g.doubleclick.net') > 0
        or strpos({{ s }}, 'doubleclick.net') > 0 then 'Display'
    when {{ m }} in ('paid_social', 'paidsocial', 'paid social', 'social_paid') then 'Paid Social'
    when {{ m }} = 'organic' then 'Organic Search'
    when {{ m }} = 'email' then 'Email'
    when {{ m }} = 'affiliate' then 'Affiliate'
    when {{ m }} in ('social', 'organic_social', 'social_organic')
        or ({{ m }} = 'referral' and (
            strpos({{ s }}, 'facebook') > 0 or strpos({{ s }}, 'instagram') > 0
            or strpos({{ s }}, 'twitter') > 0 or strpos({{ s }}, 't.co') > 0
            or strpos({{ s }}, 'linkedin') > 0 or strpos({{ s }}, 'pinterest') > 0
            or strpos({{ s }}, 'reddit') > 0)) then 'Organic Social'
    when {{ m }} = 'referral' then 'Referral'
    when {{ m }} in ('(none)', 'none') or {{ s }} in ('(direct)', 'direct') then 'Direct'
    else 'Other'
end
{%- endmacro %}
