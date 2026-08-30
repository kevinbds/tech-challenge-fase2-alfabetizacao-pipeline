from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, StringConstraints

ReleaseId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReleasePartition(BaseModel):
    """Exact manifest selected for one source and year."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str
    year: int
    run_id: ReleaseId
    manifest_uri: str


class Release(BaseModel):
    """Immutable candidate mapping across completed source partitions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    release_id: ReleaseId
    created_at: datetime
    partitions: tuple[ReleasePartition, ...]


class ActiveRelease(BaseModel):
    """Singleton active and previous release pointers."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    singleton_key: bool = True
    active_release_id: ReleaseId
    previous_release_id: ReleaseId | None
