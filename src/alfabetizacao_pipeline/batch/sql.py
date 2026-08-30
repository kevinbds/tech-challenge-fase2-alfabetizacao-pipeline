from hashlib import sha256

from alfabetizacao_pipeline.batch.models import SourceContract


def qualified_table(project: str, dataset: str, source: str) -> str:
    """Quote a trusted catalog table identifier."""
    return f"`{project}.{dataset}.{source}`"


def build_select_sql(
    contract: SourceContract,
    project: str,
    dataset: str,
    year: int,
) -> str:
    """Build an explicit-column annual partition query."""
    columns = ",\n  ".join(column.name for column in contract.columns)
    return (
        f"SELECT\n  {columns}\n"
        f"FROM {qualified_table(project, dataset, contract.name)}\n"
        f"WHERE ano = {year}"
    )


def build_fingerprint_sql(
    contract: SourceContract,
    project: str,
    dataset: str,
    year: int,
) -> str:
    """Build the canonical row-count and BIT_XOR content fingerprint query."""
    columns = ", ".join(column.name for column in contract.columns)
    return (
        "SELECT\n"
        "  COUNT(*) AS row_count,\n"
        "  BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(STRUCT("
        f"{columns})))) AS content_fingerprint\n"
        f"FROM {qualified_table(project, dataset, contract.name)}\n"
        f"WHERE ano = {year}"
    )


def build_export_sql(select_sql: str, landing_uri: str) -> str:
    """Wrap a select in a non-overwriting Snappy Parquet export."""
    return (
        "EXPORT DATA OPTIONS(\n"
        f"  uri='{landing_uri}',\n"
        "  format='PARQUET',\n"
        "  compression='SNAPPY',\n"
        "  overwrite=false\n"
        ") AS\n"
        f"{select_sql}"
    )


def stable_hash(value: str) -> str:
    """Return a deterministic SHA-256 hex digest."""
    return sha256(value.encode("utf-8")).hexdigest()


def schema_hash(contract: SourceContract) -> str:
    """Hash ordered name/type/mode tuples for one source schema."""
    canonical = "|".join(
        f"{column.name}:{column.data_type}:{column.mode}" for column in contract.columns
    )
    return stable_hash(canonical)
