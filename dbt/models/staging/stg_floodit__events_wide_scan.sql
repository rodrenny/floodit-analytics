{#
    DELIBERATE COST-POLICY VIOLATION — acceptance demo for the CI cost gate.
    Scans ~50 days of full-width events (~1.7 GiB): small enough to slip
    past the 2 GiB per-query build cap, large enough that the 1 GiB CI cost
    gate must block the PR. This model must never merge.
#}

with source as (

    select *
    from {{ source('firebase_public', 'events') }}
    where _table_suffix between '20180612' and '20180731'

)

select * from source
