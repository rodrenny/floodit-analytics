{#
    One row per user (user_pseudo_id is device-scoped — the only identifier
    in this export). first_open_at is null for users whose install predates
    the loaded window; retention cohorts only use users where it is set.
#}

with events as (

    select * from {{ ref('stg_floodit__events') }}

),

user_days as (

    select
        user_pseudo_id,
        count(*) as num_days_active
    from {{ ref('int_user_days') }}
    group by user_pseudo_id

),

sessions as (

    select
        user_pseudo_id,
        max(session_number) as num_sessions
    from {{ ref('int_events_sessionized') }}
    group by user_pseudo_id

),

per_user as (

    select
        user_pseudo_id,
        min(if(event_name = 'first_open', event_at, null)) as first_open_at,
        min(first_touch_at) as first_touch_at,
        min(event_date) as first_seen_date,
        max(event_date) as last_seen_date,
        count(*) as num_events,
        min(platform) as platform,
        array_agg(country ignore nulls order by event_at limit 1)[safe_offset(0)] as first_country,
        array_agg(acquisition_medium ignore nulls order by event_at limit 1)[safe_offset(0)]
            as acquisition_medium,
        array_agg(acquisition_source ignore nulls order by event_at limit 1)[safe_offset(0)]
            as acquisition_source,
        array_agg(initial_extra_steps ignore nulls order by event_at desc limit 1)[safe_offset(0)]
            as initial_extra_steps,
        countif(event_name = 'spend_virtual_currency') as num_spend_events,
        countif(event_name = 'app_remove') > 0 as has_uninstalled
    from events
    group by user_pseudo_id

),

final as (

    select
        per_user.user_pseudo_id,
        per_user.first_open_at,
        per_user.first_open_at is not null as has_observed_first_open,
        per_user.first_touch_at,
        per_user.first_seen_date,
        per_user.last_seen_date,
        user_days.num_days_active,
        sessions.num_sessions,
        per_user.num_events,
        per_user.platform,
        per_user.first_country,
        per_user.acquisition_medium,
        per_user.acquisition_source,
        per_user.initial_extra_steps,
        per_user.num_spend_events,
        per_user.has_uninstalled
    from per_user
    inner join user_days on per_user.user_pseudo_id = user_days.user_pseudo_id
    inner join sessions on per_user.user_pseudo_id = sessions.user_pseudo_id

)

select * from final
