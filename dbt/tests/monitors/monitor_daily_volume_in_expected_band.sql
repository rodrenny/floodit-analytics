-- Volume monitor: the export ships exactly 50,000 events per day, so a
-- deterministic band beats a trained baseline. Fires on duplicate-day
-- injections (100k) or partial loads. severity warn: monitors alert,
-- they don't halt the pipeline.

{{ config(severity='warn') }}

with daily as (

    select
        event_date,
        count(*) as num_events
    from {{ ref('stg_floodit__events') }}
    group by event_date

)

select
    event_date,
    num_events
from daily
where num_events not between 40000 and 60000
