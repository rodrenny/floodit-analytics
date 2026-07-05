-- Quality monitor: platform is never null in healthy data (verified over
-- the full range). Fires on drop-column / null-spike injections targeting
-- platform. severity warn: monitors alert, they don't halt the pipeline.

{{ config(severity='warn') }}

with daily as (

    select
        event_date,
        countif(platform is null) / count(*) as null_rate
    from {{ ref('stg_floodit__events') }}
    group by event_date

)

select
    event_date,
    round(null_rate, 4) as null_rate
from daily
where null_rate > 0.01
