from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ReleasePartition(BaseModel):
    """Exact manifest selected for one source and year."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    year: int
    run_id: str
    manifest_uri: str


class Release(BaseModel):
    """Immutable candidate mapping across completed source partitions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    release_id: str
    created_at: datetime
    partitions: tuple[ReleasePartition, ...]


class ActiveRelease(BaseModel):
    """Singleton active and previous release pointers."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    singleton_key: bool = True
    active_release_id: str
    previous_release_id: str | None
