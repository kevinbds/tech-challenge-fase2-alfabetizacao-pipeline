from collections.abc import Iterable

class Blob:
    name: str
    generation: int | str | None
    crc32c: str | None
    size: int | str | None
    def download_as_bytes(self, *, checksum: str) -> bytes: ...
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
    def blob(self, name: str) -> Blob: ...

class Client:
    def __init__(self, *, project: str) -> None: ...
    def bucket(self, bucket_name: str) -> Bucket: ...
    def list_blobs(self, bucket: str, *, prefix: str) -> Iterable[Blob]: ...
