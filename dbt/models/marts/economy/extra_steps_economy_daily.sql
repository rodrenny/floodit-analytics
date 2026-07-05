{#
    Grain: one row per day. The extra-steps economy, decoded from recon:
    spend_virtual_currency / use_extra_steps carry virtual_currency_name =
    'steps', item_name = the level number as a string, and value = steps
    spent (1..20); ad_reward.value = steps granted by a rewarded ad;
    no_more_extra_steps fires when a user runs out.
#}

with events as (

    select
        event_date,
        event_name,
        user_pseudo_id,
        event_value
    from {{ ref('fct_events') }}
    where event_name in (
        'spend_virtual_currency', 'use_extra_steps', 'no_more_extra_steps', 'ad_reward'
    )

),

daily as (

    select
        event_date,
        countif(event_name = 'spend_virtual_currency') as spend_events,
        round(sum(if(event_name = 'spend_virtual_currency', event_value, 0)), 1)
            as steps_spent,
        count(distinct if(event_name = 'spend_virtual_currency', user_pseudo_id, null))
            as spenders,
        countif(event_name = 'use_extra_steps') as use_events,
        round(sum(if(event_name = 'use_extra_steps', event_value, 0)), 1) as steps_used,
        countif(event_name = 'no_more_extra_steps') as exhaustion_events,
        count(distinct if(event_name = 'no_more_extra_steps', user_pseudo_id, null))
            as exhausted_users,
        countif(event_name = 'ad_reward') as ad_rewards,
        round(sum(if(event_name = 'ad_reward', event_value, 0)), 1) as steps_granted_by_ads
    from events
    group by event_date

)

select * from daily
