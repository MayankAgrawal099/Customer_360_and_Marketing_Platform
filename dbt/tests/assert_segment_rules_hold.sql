-- Each segment contains only customers who satisfy its stated rule (written here a second time, per segment,
-- as the rule is worded in dim_customer_segments), so the CASE in the model cannot drift from the definitions.
select customer_id, segment from {{ ref('fct_customer_segments') }}
where case segment
    when 'Champions'        then coalesce(not (r_score between 4 and 5 and f_score >= 3), true)
    when 'Loyal'            then coalesce(not (f_score >= 2 and r_score between 3 and 5 and not (r_score >= 4 and f_score >= 3)), true)
    when 'At Risk'          then coalesce(not (f_score >= 2 and r_score between 1 and 2), true)
    when 'Big Spenders'     then coalesce(not (f_score = 1 and r_score between 3 and 5 and m_score between 4 and 5), true)
    when 'New Customers'    then coalesce(not (f_score = 1 and r_score between 4 and 5 and m_score between 1 and 3), true)
    when 'Promising'        then coalesce(not (f_score = 1 and r_score = 3 and m_score between 1 and 3), true)
    when 'Needs Attention'  then coalesce(not (f_score = 1 and r_score = 2), true)
    when 'Lost'             then coalesce(not (f_score = 1 and r_score = 1), true)
    when 'No Purchase Yet'  then coalesce(not (r_score is null and orders = 0 and historical_net_revenue_usd = 0), true)
    else true end
