from enum import StrEnum, unique
from typing import NewType

ProjectId = NewType("ProjectId", str)
BytesBilled = NewType("BytesBilled", int)


@unique
class OutputFormat(StrEnum):
    """Serialization formats supported by machine-facing commands."""

    JSON = "json"
