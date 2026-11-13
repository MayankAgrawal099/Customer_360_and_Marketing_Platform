-- Scores must follow the values: a better value never gets a lower score, equal values share a score,
-- and every score stays between 1 and 5. Checked by comparing the value ranges of neighbouring scores.
with ranges as (
    select 'recency' as measure, r_score as score,
           min(-recency_days * 1.0) as low, max(-recency_days * 1.0) as high from {{ ref('fct_customer_rfm') }} group by r_score
    union all
    select 'frequency', f_score, min(frequency * 1.0), max(frequency * 1.0) from {{ ref('fct_customer_rfm') }} group by f_score
    union all
    select 'monetary', m_score, min(monetary_usd), max(monetary_usd) from {{ ref('fct_customer_rfm') }} group by m_score
),
ordered as (
    select *, lag(high) over (partition by measure order by score) as previous_high from ranges
)
select measure, cast(score as string) from ordered
where score not between 1 and 5
   or (previous_high is not null and low <= previous_high)
union all
select 'row', customer_id from {{ ref('fct_customer_rfm') }}
where rfm_total != r_score + f_score + m_score
   or rfm_code != concat(cast(r_score as string), cast(f_score as string), cast(m_score as string))
   or f_score != least(frequency, 5)
