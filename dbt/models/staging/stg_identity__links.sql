-- One row per GA4 device linked to a customer by the identity-resolution rules (docs/identity_resolution.md).

select
    user_pseudo_id,
    customer_id,
    link_rule,
    evidence_rules,
    confidence,
    evidence_count,
    first_evidence_ts,
    had_conflict
from {{ source('identity', 'identity_links') }}
