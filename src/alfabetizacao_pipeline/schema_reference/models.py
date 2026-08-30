from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ReferenceSchemaDescriptor(BaseModel):
    """Content-addressed zero-row Parquet reference schema location."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    schema_hash: str
    local_path: Path
    reference_file_schema_uri: str


class ReferenceSchemaInspection(BaseModel):
    """Observable row count and ordered column names read from Parquet."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    row_count: int
    column_names: tuple[str, ...]
