{#
    Extracts a single key from a GA4 key-value array (event_params or
    user_properties). The one place param-unnesting logic lives — do not
    hand-roll unnest subqueries in models.

    value_type:
        string  -> value.string_value
        int     -> value.int_value
        float   -> float_value/double_value (GA4 uses either, never both)
        numeric -> any numeric slot, as float64 (for params whose type
                   varies by event, e.g. `value` and `level`)
#}
{% macro extract_param(key, value_type='string', column='event_params') %}
    {%- set value_exprs = {
        'string': 'value.string_value',
        'int': 'value.int_value',
        'float': 'coalesce(value.float_value, value.double_value)',
        'numeric': 'coalesce(cast(value.int_value as float64), value.float_value, value.double_value)',
    } -%}
    (select {{ value_exprs[value_type] }} from unnest({{ column }}) where key = '{{ key }}')
{%- endmacro %}
