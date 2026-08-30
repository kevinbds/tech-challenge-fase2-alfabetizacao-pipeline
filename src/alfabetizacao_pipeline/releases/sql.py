import re

from alfabetizacao_pipeline.batch.errors import InvalidTableIdentifierError


def _assert_singleton(table: str) -> str:
    quoted = _quoted_table(table)
    template = "ASSERT (SELECT COUNT(*) FROM TABLE_NAME WHERE singleton_key = TRUE) = 1;"
    return template.replace("TABLE_NAME", quoted)


def promotion_sql(table: str) -> str:
    """Build parameterized DML-only singleton promotion transaction."""
    quoted = _quoted_table(table)
    return "\n".join(
        (
            "BEGIN TRANSACTION;",
            _assert_singleton(table),
            "UPDATE " + quoted,
            "SET previous_release_id = active_release_id,",
            "    active_release_id = @candidate_release_id,",
            "    promoted_at = CURRENT_TIMESTAMP()",
            "WHERE singleton_key = TRUE;",
            "COMMIT TRANSACTION;",
        )
    )


def rollback_sql(table: str) -> str:
    """Build DML-only rollback that swaps active and previous pointers."""
    quoted = _quoted_table(table)
    return "\n".join(
        (
            "BEGIN TRANSACTION;",
            _assert_singleton(table),
            "UPDATE " + quoted,
            "SET active_release_id = previous_release_id,",
            "    previous_release_id = active_release_id,",
            "    promoted_at = CURRENT_TIMESTAMP()",
            "WHERE singleton_key = TRUE;",
            "COMMIT TRANSACTION;",
        )
    )


def _quoted_table(table: str) -> str:
    if (
        re.fullmatch(r"[a-z][a-z0-9-]{4,29}\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table)
        is None
    ):
        raise InvalidTableIdentifierError(table=table)
    return "`" + table + "`"
