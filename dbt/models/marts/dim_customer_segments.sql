-- The segment definitions, one row per segment: the rule in plain words, the rule as it is applied, and the
-- action marketing should take. fct_customer_segments joins to this table, so a segment that is not defined
-- here cannot exist. The same text is in docs/customer_segments.md (a test keeps the two in step).
-- Rules are checked top to bottom (segment_order); the first rule that matches wins.

select 1 as segment_order, 'Champions' as segment,
       'Bought recently and often.' as definition,
       'recency score 4-5 and 3 or more orders' as rule,
       'Reward them, ask for reviews, offer early access. Do not discount.' as action
union all
select 2, 'Loyal',
       'Repeat buyers who are still active.',
       '2 or more orders and recency score 3-5 (and not a Champion)',
       'Cross-sell and loyalty offers to grow the basket.'
union all
select 3, 'At Risk',
       'Repeat buyers who have gone quiet.',
       '2 or more orders and recency score 1-2',
       'Win-back campaign with a personal message. Best return on effort: they have shown they will buy again.'
union all
select 4, 'Big Spenders',
       'One order, recent enough, and in the top 40% of spend.',
       '1 order, recency score 3-5 and monetary score 4-5',
       'Invite a second purchase with related premium products.'
union all
select 5, 'New Customers',
       'One very recent order of ordinary size.',
       '1 order, recency score 4-5 and monetary score 1-3',
       'Welcome series and a nudge towards the second order.'
union all
select 6, 'Promising',
       'One order, mid recency, ordinary size.',
       '1 order, recency score 3 and monetary score 1-3',
       'Time-limited offer to bring them back before they drift.'
union all
select 7, 'Needs Attention',
       'One order, now getting old.',
       '1 order and recency score 2',
       'Reminder with best sellers before they lapse.'
union all
select 8, 'Lost',
       'One order, the oldest in the data.',
       '1 order and recency score 1',
       'Low-cost reactivation only; keep out of paid campaigns.'
union all
select 9, 'No Purchase Yet',
       'A customer account with no order.',
       'no orders (not scored by RFM)',
       'First-order incentive. Check marketing_opt_in before contacting.'
