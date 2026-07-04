{%- set is_prod = target.name == 'prod' -%}
{%- set suffix_start = var('full_start_date') if is_prod else var('dev_start_date') -%}
{%- set suffix_end = var('full_end_date') if is_prod else var('dev_end_date') -%}

with source as (

    select *
    from {{ source('firebase_public', 'events') }}
    where _table_suffix between '{{ suffix_start }}' and '{{ suffix_end }}'

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
        -- happens downstream from session_start + engagement gaps)
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
        ) as initial_extra_steps

    from source

),

numbered as (

    -- GA4 has no event id and identical events can share a microsecond;
    -- the repeat number makes the surrogate key collision-proof.
    select
        *,
        row_number() over (
            partition by user_pseudo_id, event_at, event_name
        ) as event_repeat_number
    from renamed

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key(
            ['user_pseudo_id', 'event_at', 'event_name', 'event_repeat_number']
        ) }} as event_pk,
        *
    from numbered

)

select * from final
