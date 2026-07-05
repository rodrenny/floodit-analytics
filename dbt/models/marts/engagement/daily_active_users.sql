{#
    Grain: one row per calendar day with activity. DAU counts any user with
    at least one event that day; new users are those on their first-ever
    observed day (first_seen_date), which overstates "new" for the first
    loaded days of the replay window — documented in the YAML.
#}

with user_days as (

    select * from {{ ref('int_user_days') }}

),

users as (

    select
        user_pseudo_id,
        first_seen_date
    from {{ ref('dim_users') }}

),

daily as (

    select
        user_days.event_date as activity_date,
        count(distinct user_days.user_pseudo_id) as dau,
        count(distinct if(
            users.first_seen_date = user_days.event_date, user_days.user_pseudo_id, null
        )) as new_users,
        sum(user_days.num_sessions) as num_sessions,
        sum(user_days.num_events) as num_events,
        round(sum(user_days.engagement_minutes), 1) as engagement_minutes,
        count(distinct if(user_days.has_played_quickplay, user_days.user_pseudo_id, null))
            as quickplay_users,
        count(distinct if(user_days.has_played_progressive, user_days.user_pseudo_id, null))
            as progressive_users
    from user_days
    inner join users on user_days.user_pseudo_id = users.user_pseudo_id
    group by activity_date

),

final as (

    select
        activity_date,
        dau,
        new_users,
        dau - new_users as returning_users,
        num_sessions,
        num_events,
        engagement_minutes,
        quickplay_users,
        progressive_users
    from daily

)

select * from final
