{#
    Sessionization without ga_session_id (this 2018 export predates the
    param): a new session starts on a user's first event or after 30+
    minutes of inactivity — the same timeout GA4 itself uses. session_start
    events exist in the data but only mark app-open, not resumption, so the
    gap rule is the source of truth.
#}

with events as (

    select
        event_pk,
        user_pseudo_id,
        event_at,
        event_date
    from {{ ref('stg_floodit__events') }}

),

gapped as (

    select
        *,
        timestamp_diff(
            event_at,
            lag(event_at) over (partition by user_pseudo_id order by event_at),
            second
        ) as seconds_since_previous_event
    from events

),

flagged as (

    select
        *,
        coalesce(
            seconds_since_previous_event is null
            or seconds_since_previous_event > 30 * 60,
            false
        ) as is_session_first_event
    from gapped

),

numbered as (

    select
        *,
        sum(cast(is_session_first_event as int64)) over (
            partition by user_pseudo_id
            order by event_at
            rows between unbounded preceding and current row
        ) as session_number
    from flagged

),

final as (

    select
        event_pk,
        user_pseudo_id,
        event_at,
        event_date,
        session_number,
        is_session_first_event,
        seconds_since_previous_event,
        {{ dbt_utils.generate_surrogate_key(['user_pseudo_id', 'session_number']) }} as session_id
    from numbered

)

select * from final
