BEGIN TRANSACTION;
ASSERT (
    SELECT COUNT(*)
    FROM `PROJECT_ID.ops.active_release`
    WHERE singleton_key = TRUE
) = 1;
ASSERT (
    SELECT previous_release_id IS NOT NULL
    FROM `PROJECT_ID.ops.active_release`
    WHERE singleton_key = TRUE
);
UPDATE `PROJECT_ID.ops.active_release`
SET
    active_release_id = previous_release_id,
    previous_release_id = active_release_id,
    promoted_at = CURRENT_TIMESTAMP()
WHERE singleton_key = TRUE;
COMMIT TRANSACTION;
