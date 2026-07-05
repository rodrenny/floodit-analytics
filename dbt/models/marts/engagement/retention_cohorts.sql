{#
    Grain: one row per first_open cohort date. Classic day-N retention:
    a user counts as retained on day N iff they were active exactly N days
    after their first_open. Rates are null when the horizon is not yet
    observable (cohort_date + N beyond the loaded window) — never zero.
#}

with users as (

    select
        user_pseudo_id,
        date(first_open_at) as cohort_date
    from {{ ref('dim_users') }}
    where has_observed_first_open

),

user_days as (

    select
        user_pseudo_id,
        event_date
    from {{ ref('int_user_days') }}

),

window_bounds as (

    select max(event_date) as max_loaded_date
    from user_days

),

retained as (

    select
        users.cohort_date,
        users.user_pseudo_id,
        countif(user_days.event_date = date_add(users.cohort_date, interval 1 day)) > 0
            as is_retained_d1,
        countif(user_days.event_date = date_add(users.cohort_date, interval 7 day)) > 0
            as is_retained_d7,
        countif(user_days.event_date = date_add(users.cohort_date, interval 30 day)) > 0
            as is_retained_d30
    from users
    inner join user_days on users.user_pseudo_id = user_days.user_pseudo_id
    group by users.cohort_date, users.user_pseudo_id

),

cohorts as (

    select
        retained.cohort_date,
        count(*) as cohort_size,
        countif(retained.is_retained_d1) as retained_d1,
        countif(retained.is_retained_d7) as retained_d7,
        countif(retained.is_retained_d30) as retained_d30
    from retained
    group by retained.cohort_date

),

final as (

    select
        cohorts.cohort_date,
        cohorts.cohort_size,
        cohorts.retained_d1,
        cohorts.retained_d7,
        cohorts.retained_d30,
        if(
            date_add(cohorts.cohort_date, interval 1 day) <= window_bounds.max_loaded_date,
            round(cohorts.retained_d1 / cohorts.cohort_size, 4), null
        ) as retention_d1,
        if(
            date_add(cohorts.cohort_date, interval 7 day) <= window_bounds.max_loaded_date,
            round(cohorts.retained_d7 / cohorts.cohort_size, 4), null
        ) as retention_d7,
        if(
            date_add(cohorts.cohort_date, interval 30 day) <= window_bounds.max_loaded_date,
            round(cohorts.retained_d30 / cohorts.cohort_size, 4), null
        ) as retention_d30
    from cohorts
    cross join window_bounds

)

select * from final
