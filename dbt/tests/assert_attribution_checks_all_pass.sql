-- Every recorded attribution check passes, and the table really holds the checks (it cannot pass by being empty):
-- 4 models x 6 per-model checks, 2 first/last checks x 2 models, the unknown-source checks and the two overall checks.
select check_name, model from {{ ref('fct_attribution_checks') }} where not passed
union all
select 'too few checks recorded', cast(n as string)
from (select count(*) as n from {{ ref('fct_attribution_checks') }})
where n < 30
