from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RetryEvent:
    """Observable decision emitted before a retryable operation is repeated."""

    operation: str
    attempt: int
    maximum_attempts: int


class RetryObserver(Protocol):
    """Consumer boundary for retry metrics or structured logs."""

    def retrying(self, event: RetryEvent) -> None:
        """Record one retry decision without payload contents."""
        ...


class NullRetryObserver:
    """Default observer for deployments without a metrics consumer."""

    def retrying(self, event: RetryEvent) -> None:
        """Accept an event while producing no side effect."""
        del event


def retry_call[ResultT](
    operation: str,
    action: Callable[[], ResultT],
    *,
    retryable: tuple[type[Exception], ...],
    maximum_attempts: int = 3,
    observer: RetryObserver | None = None,
) -> ResultT:
    """Execute with an explicit attempt bound and observable retry decisions."""
    if maximum_attempts < 1:
        raise ValueError(maximum_attempts)
    consumer = observer or NullRetryObserver()
    for attempt in range(1, maximum_attempts + 1):
        try:
            return action()
        except retryable:
            if attempt == maximum_attempts:
                raise
            consumer.retrying(RetryEvent(operation, attempt, maximum_attempts))
    raise RuntimeError(operation)
