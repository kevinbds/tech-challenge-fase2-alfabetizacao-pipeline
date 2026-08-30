from dataclasses import dataclass
from enum import StrEnum, unique
from typing import TYPE_CHECKING, assert_never


@unique
class JobState(StrEnum):
    """Estados relevantes de um job streaming temporário."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    DRAINED = "DRAINED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class PollPolicy:
    """Estado alvo e limite determinístico de polling."""

    target: JobState
    max_polls: int


@dataclass(frozen=True, slots=True)
class PollResult:
    """Resultado terminal observado pela orquestração."""

    success: bool
    cancel_required: bool
    final_state: JobState


def evaluate_poll(states: tuple[JobState, ...], policy: PollPolicy) -> PollResult:
    """Avalia uma sequência sem tratar cancelamento como sucesso."""
    observed = states[: policy.max_polls]
    for state in observed:
        match state:
            case JobState.DRAINED if policy.target is JobState.DRAINED:
                return PollResult(success=True, cancel_required=False, final_state=state)
            case JobState.RUNNING if policy.target is JobState.RUNNING:
                return PollResult(success=True, cancel_required=False, final_state=state)
            case JobState.CANCELLED | JobState.FAILED:
                return PollResult(success=False, cancel_required=False, final_state=state)
            case JobState.PENDING | JobState.RUNNING | JobState.DRAINING | JobState.DRAINED:
                continue
            case _ as unreachable if not TYPE_CHECKING:
                assert_never(unreachable)
    final_state = observed[-1] if observed else JobState.PENDING
    return PollResult(success=False, cancel_required=True, final_state=final_state)
