{#
    Retention D1/D7/D30 by extra-steps starting-grant bucket.
    Spec: specs/ticket_001_extra_steps_d7_retention.md.
    Each day-N rate uses its own observable-horizon denominator so buckets
    stay comparable while the replay is mid-window; a rate is null (never 0)
    when its denominator is 0.
#}

with users as (

    select
        user_pseudo_id,
        date(first_open_at) as cohort_date,
        initial_extra_steps
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

bucketed as (

    select
        user_pseudo_id,
        cohort_date,
        coalesce(cast(initial_extra_steps as string), 'unassigned') as grant_bucket
    from users

),

user_retention as (

    select
        bucketed.grant_bucket,
        bucketed.user_pseudo_id,
        bucketed.cohort_date,
        max(if(
            user_days.event_date = date_add(bucketed.cohort_date, interval 1 day), 1, 0
        )) as is_retained_d1,
        max(if(
            user_days.event_date = date_add(bucketed.cohort_date, interval 7 day), 1, 0
        )) as is_retained_d7,
        max(if(
            user_days.event_date = date_add(bucketed.cohort_date, interval 30 day), 1, 0
        )) as is_retained_d30
    from bucketed
    inner join user_days on bucketed.user_pseudo_id = user_days.user_pseudo_id
    group by bucketed.grant_bucket, bucketed.user_pseudo_id, bucketed.cohort_date

),

aggregated as (

    select
        user_retention.grant_bucket,
        count(*) as cohort_users,
        countif(
            date_add(user_retention.cohort_date, interval 1 day) <= window_bounds.max_loaded_date
        ) as d1_denominator,
        countif(
            date_add(user_retention.cohort_date, interval 7 day) <= window_bounds.max_loaded_date
        ) as d7_denominator,
        countif(
            date_add(user_retention.cohort_date, interval 30 day) <= window_bounds.max_loaded_date
        ) as d30_denominator,
        sum(user_retention.is_retained_d1) as retained_d1,
        sum(user_retention.is_retained_d7) as retained_d7,
        sum(user_retention.is_retained_d30) as retained_d30
    from user_retention
    cross join window_bounds
    group by user_retention.grant_bucket

),

final as (

    select
        grant_bucket,
        cohort_users,
        d1_denominator,
        d7_denominator,
        d30_denominator,
        retained_d1,
        retained_d7,
        retained_d30,
        if(d1_denominator > 0, round(retained_d1 / d1_denominator, 4), null) as retention_d1,
        if(d7_denominator > 0, round(retained_d7 / d7_denominator, 4), null) as retention_d7,
        if(d30_denominator > 0, round(retained_d30 / d30_denominator, 4), null) as retention_d30
    from aggregated

)

select * from final
