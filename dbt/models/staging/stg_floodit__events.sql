{#
    prod reads the replayed raw table (partition filter mandatory);
    dev/ci read the public shards directly on the bounded dev slice.
    Pseudo-columns are excluded from select *, so both branches yield
    the identical GA4 shard schema.
#}
{%- if target.name == 'prod' -%}
    {%- set src = source('raw_floodit', 'events') -%}
    {%- set day_filter = "_partitiondate between parse_date('%Y%m%d', '"
        ~ var('full_start_date') ~ "') and parse_date('%Y%m%d', '" ~ var('full_end_date') ~ "')" -%}
{%- else -%}
    {%- set src = source('firebase_public', 'events') -%}
    {%- set day_filter = "_table_suffix between '" ~ var('dev_start_date')
        ~ "' and '" ~ var('dev_end_date') ~ "'" -%}
{%- endif %}

with source as (

    select *
    from {{ src }}
    where {{ day_filter }}

),

renamed as (

    select
        -- event identity & timing
        parse_date('%Y%m%d', event_date) as event_date,
        timestamp_micros(event_timestamp) as event_at,
        event_name,

        -- user (user_id is 100% null in this export; user_pseudo_id is the
        -- device-scoped identifier and is never null)
        user_pseudo_id,
        timestamp_micros(user_first_touch_timestamp) as first_touch_at,

        -- device / geo / app context
        platform,
        device.category as device_category,
        device.operating_system as device_os,
        device.language as device_language,
        geo.country,
        app_info.version as app_version,

        -- acquisition
        traffic_source.name as acquisition_campaign,
        traffic_source.medium as acquisition_medium,
        traffic_source.source as acquisition_source,

        -- event_params (this export predates ga_session_id: sessionization
        -- happens downstream from session_start + engagement gaps).
        -- board is only set on *_quickplay events; progressive-mode events
        -- carry level_number/level_name instead.
        {{ extract_param('engagement_time_msec', 'int') }} as engagement_time_msec,
        {{ extract_param('board', 'string') }} as board,
        cast({{ extract_param('level', 'numeric') }} as int64) as level_number,
        {{ extract_param('level_name', 'string') }} as level_name,
        {{ extract_param('score', 'numeric') }} as score,
        {{ extract_param('value', 'numeric') }} as event_value,
        {{ extract_param('virtual_currency_name', 'string') }} as virtual_currency_name,
        {{ extract_param('item_name', 'string') }} as item_name,
        {{ extract_param('firebase_screen_class', 'string') }} as screen_class,
        {{ extract_param('firebase_screen', 'string') }} as screen_name,

        -- user_properties (stored as strings in GA4)
        safe_cast(
            {{ extract_param('initial_extra_steps', 'string', column='user_properties') }}
            as int64
        ) as initial_extra_steps,

        -- raw event_params JSON: part of the content key below, then dropped.
        to_json_string(event_params) as event_params_json

    from source

),

keyed as (

    -- event_pk is the identity of the full normalized payload: a hash of
    -- every output column plus the event_params JSON. Because it hashes the
    -- whole payload, two rows share a key only when they are identical in
    -- every attribute this model keeps — so the dedup below can never pick
    -- arbitrarily between rows that actually differ (the earlier key, over
    -- just user/event_at/event_name/params, could). Every hashed field is
    -- derived only from original GA4 columns, so the key is identical across
    -- the dev (public shard) and prod (raw superset) sources.
    --
    -- GA4 has no native event id and occasionally re-delivers an event with
    -- only server-side metadata differing (e.g. event_server_timestamp_offset,
    -- which this model does not keep) — those re-deliveries are byte-identical
    -- in the payload and collapse deterministically.
    select
        to_hex(md5(to_json_string(renamed))) as event_pk,
        renamed.* except (event_params_json)
    from renamed

),

final as (

    select *
    from keyed
    qualify row_number() over (partition by event_pk) = 1

)

select * from final
