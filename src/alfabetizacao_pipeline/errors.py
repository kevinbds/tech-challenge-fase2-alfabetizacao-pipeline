from enum import IntEnum, unique


@unique
class ExitCode(IntEnum):
    """Stable process outcomes consumed by automation and orchestration."""

    SUCCESS = 0
    INVALID_CONFIGURATION = 2
    COST_LIMIT_EXCEEDED = 3
    CRITICAL_QUALITY_FAILURE = 4
    OPERATIONAL_FAILURE = 5
