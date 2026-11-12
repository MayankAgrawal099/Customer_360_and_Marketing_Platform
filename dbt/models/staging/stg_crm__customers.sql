-- One row per synthetic CRM customer, typed and tidied.

select
    customer_id,
    first_name,
    last_name,
    concat(first_name, ' ', last_name) as full_name,
    lower(email) as email,
    email_sha256,
    phone,
    country,
    created_at,
    date(created_at) as created_date,
    marketing_opt_in
from {{ source('raw', 'crm_customers') }}
