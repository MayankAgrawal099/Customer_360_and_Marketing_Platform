-- App orders never happen on the website, so they cannot carry a GA4 transaction id.
select order_id
from {{ ref('stg_crm__orders') }}
where order_channel = 'app' and ga_transaction_id is not null
