{#
    User-day spine: one row per user per active day, with the day's
    activity rolled up. Feeds daily_active_users and retention_cohorts.
#}

with events as (

    select
        user_pseudo_id,
        event_date,
        event_name,
        engagement_time_msec
    from {{ ref('stg_floodit__events') }}

),

sessions as (

    select
        user_pseudo_id,
        event_date,
        session_id
    from {{ ref('int_events_sessionized') }}

),

daily_events as (

    select
        user_pseudo_id,
        event_date,
        count(*) as num_events,
        countif(event_name = 'first_open') > 0 as has_first_open,
        countif(event_name like '%_quickplay') > 0 as has_played_quickplay,
        countif(event_name in (
            'level_start', 'level_end', 'level_complete', 'level_fail',
            'level_retry', 'level_reset', 'level_up'
        )) > 0 as has_played_progressive,
        countif(event_name = 'spend_virtual_currency') > 0 as has_spent_steps,
        round(sum(engagement_time_msec) / 60000, 2) as engagement_minutes
    from events
    group by user_pseudo_id, event_date

),

daily_sessions as (

    select
        user_pseudo_id,
        event_date,
        count(distinct session_id) as num_sessions
    from sessions
    group by user_pseudo_id, event_date

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key(
            ['daily_events.user_pseudo_id', 'daily_events.event_date']
        ) }} as user_day_pk,
        daily_events.user_pseudo_id,
        daily_events.event_date,
        daily_events.num_events,
        daily_sessions.num_sessions,
        daily_events.has_first_open,
        daily_events.has_played_quickplay,
        daily_events.has_played_progressive,
        daily_events.has_spent_steps,
        daily_events.engagement_minutes
    from daily_events
    inner join daily_sessions
        on
            daily_events.user_pseudo_id = daily_sessions.user_pseudo_id
            and daily_events.event_date = daily_sessions.event_date

)

select * from final
