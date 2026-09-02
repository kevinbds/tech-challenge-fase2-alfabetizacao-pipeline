from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ReferenceSchemaDescriptor(BaseModel):
    """Content-addressed local zero-row Parquet reference schema artifact."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    schema_hash: str
    local_path: Path


class ReferenceSchemaInspection(BaseModel):
    """Observable row count and ordered column names read from Parquet."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    row_count: int
    column_names: tuple[str, ...]
