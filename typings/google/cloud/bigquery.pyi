from collections.abc import ItemsView, Iterable
from datetime import datetime

type Scalar = str | int | float | bool | datetime | None

class ScalarQueryParameter:
    name: str
    type_: str
    value: int | str
    def __init__(self, name: str, type_: str, value: int | str) -> None: ...

class QueryJobConfig:
    dry_run: bool
    use_query_cache: bool
    maximum_bytes_billed: int
    query_parameters: list[ScalarQueryParameter]
    def __init__(
        self,
        *,
        dry_run: bool = ...,
        use_query_cache: bool = ...,
        maximum_bytes_billed: int = ...,
        query_parameters: list[ScalarQueryParameter] = ...,
    ) -> None: ...

class Row:
    def __getitem__(self, key: str) -> Scalar: ...
    def items(self) -> ItemsView[str, Scalar]: ...

class RowIterator(Iterable[Row]): ...

class QueryJob:
    total_bytes_processed: int | None
    def result(self) -> RowIterator: ...

class Dataset:
    location: str | None

class Table:
    modified: datetime | None
    etag: str | None

class Client:
    def __init__(self, *, project: str) -> None: ...
    def get_dataset(self, dataset_ref: str) -> Dataset: ...
    def get_table(self, table_ref: str) -> Table: ...
    def query(
        self,
        query: str,
        *,
        job_config: QueryJobConfig,
        location: str,
        job_id: str | None = ...,
    ) -> QueryJob: ...
