-- daily_active_users must agree with the user-day spine it is built from:
-- any drift means the mart's aggregation logic broke. Returns violating days.

with spine as (

    select
        event_date,
        count(distinct user_pseudo_id) as spine_dau
    from {{ ref('int_user_days') }}
    group by event_date

),

mart as (

    select
        activity_date,
        dau
    from {{ ref('daily_active_users') }}

)

select
    mart.activity_date,
    mart.dau,
    spine.spine_dau
from mart
inner join spine on mart.activity_date = spine.event_date
where mart.dau != spine.spine_dau
