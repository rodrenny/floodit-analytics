{#
    Grain: one row per day per quickplay board size (S/M/L). Progressive
    mode is out of scope here — its levels are a linear campaign, not a
    funnel; see level_number/level_name on fct_events for that analysis.
    Invariants completes <= starts and ends <= starts verified across all
    114 available days before being encoded as tests.
#}

with events as (

    select
        event_date,
        event_name,
        board,
        user_pseudo_id
    from {{ ref('fct_events') }}
    where event_name like 'level%_quickplay' and board is not null

),

daily as (

    select
        event_date,
        board,
        countif(event_name = 'level_start_quickplay') as starts,
        countif(event_name = 'level_end_quickplay') as ends,
        countif(event_name = 'level_complete_quickplay') as completes,
        countif(event_name = 'level_fail_quickplay') as fails,
        countif(event_name = 'level_retry_quickplay') as retries,
        countif(event_name = 'level_reset_quickplay') as resets,
        count(distinct if(event_name = 'level_start_quickplay', user_pseudo_id, null))
            as users_starting
    from events
    group by event_date, board

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key(['event_date', 'board']) }} as funnel_day_pk,
        event_date,
        board,
        starts,
        ends,
        completes,
        fails,
        retries,
        resets,
        users_starting,
        if(starts > 0, round(completes / starts, 4), null) as completion_rate
    from daily

)

select * from final
