from collections.abc import Iterable

class Blob:
    name: str
    generation: int | str | None
    metageneration: int | str | None
    crc32c: str | None
    size: int | str | None
    def download_as_bytes(
        self,
        *,
        checksum: str,
        if_generation_match: int,
        if_metageneration_match: int,
    ) -> bytes: ...
    def upload_from_string(
        self,
        payload: bytes,
        *,
        if_generation_match: int,
        checksum: str,
        retry: None,
    ) -> None: ...
    def reload(self) -> None: ...

class Bucket:
    def blob(self, name: str, generation: int | None = None) -> Blob: ...

class Client:
    def __init__(self, *, project: str) -> None: ...
    def bucket(self, bucket_name: str) -> Bucket: ...
    def list_blobs(self, bucket: str, *, prefix: str) -> Iterable[Blob]: ...
