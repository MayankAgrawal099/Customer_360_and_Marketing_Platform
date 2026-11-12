-- Where an identify event carries an email hash, it must equal the hash of the customer it names.
-- (The identity rules reject conflicting events; this checks the raw data is clean.)
select i.message_id, i.customer_id
from {{ ref('stg_segment__identifies') }} i
join {{ ref('stg_crm__customers') }} c using (customer_id)
where i.email_sha256 is not null and i.email_sha256 != c.email_sha256
