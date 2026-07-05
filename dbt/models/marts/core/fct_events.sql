{{
    config(
        materialized='incremental',
        incremental_strategy='insert_overwrite',
        partition_by={'field': 'event_date', 'data_type': 'date'},
        on_schema_change='fail',
    )
}}

{#
    One row per event, session-attributed. Incremental at daily grain:
    insert_overwrite rewrites the last 2 loaded days each run so sessions
    that cross midnight settle once the following day arrives.
#}

with events as (

    select * from {{ ref('stg_floodit__events') }}

),

sessions as (

    select
        event_pk,
        session_id
    from {{ ref('int_events_sessionized') }}

),

joined as (

    select
        events.event_pk,
        events.event_date,
        events.event_at,
        events.event_name,
        events.user_pseudo_id,
        sessions.session_id,
        events.platform,
        events.device_category,
        events.device_os,
        events.country,
        events.app_version,
        events.board,
        events.level_number,
        events.level_name,
        events.score,
        events.event_value,
        events.virtual_currency_name,
        events.item_name,
        events.screen_class,
        events.engagement_time_msec,
        events.initial_extra_steps
    from events
    inner join sessions on events.event_pk = sessions.event_pk
    {% if is_incremental() %}
        where events.event_date >= (
            select date_sub(max(existing.event_date), interval 1 day)
            from {{ this }} as existing
        )
    {% endif %}

)

select * from joined
