from alfabetizacao_pipeline.batch.models import SchemaDriftReport, SourceColumn, SourceContract


def compare_schema(
    expected: SourceContract,
    actual: tuple[SourceColumn, ...],
) -> SchemaDriftReport:
    """Classify additive fields as warnings and incompatible drift as blocking."""
    expected_by_name = {column.name: column for column in expected.columns}
    actual_by_name = {column.name: column for column in actual}
    removed = tuple(sorted(expected_by_name.keys() - actual_by_name.keys()))
    added = tuple(sorted(actual_by_name.keys() - expected_by_name.keys()))
    shared = expected_by_name.keys() & actual_by_name.keys()
    type_changes = tuple(
        sorted(
            name
            for name in shared
            if expected_by_name[name].data_type != actual_by_name[name].data_type
        )
    )
    mode_changes = tuple(
        sorted(name for name in shared if expected_by_name[name].mode != actual_by_name[name].mode)
    )
    return SchemaDriftReport(
        blocking=bool(removed or type_changes or mode_changes),
        removed_columns=removed,
        added_columns=added,
        type_changes=type_changes,
        mode_changes=mode_changes,
    )
