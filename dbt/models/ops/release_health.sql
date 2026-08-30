select
    registry.release_id,
    registry.status,
    registry.created_at,
    registry.completed_at,
    active.release_id = registry.release_id as is_active
from {{ source('ops', 'release_registry') }} as registry
cross join {{ source('ops', 'active_release') }} as active
where active.singleton_key = true
