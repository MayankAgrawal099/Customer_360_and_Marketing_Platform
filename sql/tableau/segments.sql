-- Tableau extract: the nine segment definitions (one row per segment) for the segment guide table.
select segment_order, segment, definition, rule, action
from `da02-customer360.marts.dim_customer_segments`
