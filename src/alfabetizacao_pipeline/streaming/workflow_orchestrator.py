from dataclasses import dataclass
from enum import StrEnum, unique
from typing import ClassVar, Protocol, override


@unique
class FailurePoint(StrEnum):
    """Etapas em que o simulador pode injetar uma falha determinística."""

    NONE = "none"
    PRODUCER = "producer"
    STAGE = "stage"
    RAW_STALE = "raw_stale"
    MERGE = "merge"
    BACKLOG = "backlog"


@unique
class WorkflowJobState(StrEnum):
    """Estados relevantes do job durante cleanup bounded."""

    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    DRAINED = "DRAINED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        """Retorne se o estado é terminal."""
        return self in {self.DRAINED, self.CANCELLED, self.FAILED}


@dataclass(frozen=True, slots=True)
class WorkflowExecutionError(Exception):
    """Falha de etapa que preserva a causa após o cleanup."""

    failure: FailurePoint

    @override
    def __str__(self) -> str:
        """Retorne uma mensagem sem dados do evento."""
        return f"streaming workflow failed at {self.failure.value}"


@dataclass(frozen=True, slots=True)
class WorkflowCleanupError(Exception):
    """Falha interna de cleanup que não pode mascarar a causa primária."""

    @override
    def __str__(self) -> str:
        """Retorne uma mensagem sem dados do evento."""
        return "streaming workflow cleanup failed"


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Resultado terminal da demonstração."""

    success: bool
    final_state: WorkflowJobState


class WorkflowPort(Protocol):
    """Porta mínima para testar cleanup sem chamar a nuvem."""

    @property
    def final_state(self) -> WorkflowJobState:
        """Exponha o estado atual."""
        ...

    def ensure_step(self, step: FailurePoint) -> None:
        """Execute uma etapa verificável."""
        ...

    def request_drain(self) -> None:
        """Solicite drain."""
        ...

    def request_cancel(self) -> None:
        """Solicite cancelamento."""
        ...

    def wait_terminal(self) -> None:
        """Aguarde terminalidade bounded."""
        ...


class InMemoryWorkflowPort:
    """Porta determinística usada para exercitar a máquina de estados local."""

    __slots__: ClassVar[tuple[str, ...]] = (
        "cancel_requested",
        "cleanup_waited",
        "drain_requested",
        "fail_cleanup",
        "failure",
        "final_state",
    )
    failure: FailurePoint
    final_state: WorkflowJobState
    cancel_requested: bool
    drain_requested: bool
    cleanup_waited: bool
    fail_cleanup: bool

    def __init__(
        self,
        failure: FailurePoint = FailurePoint.NONE,
        *,
        fail_cleanup: bool = False,
    ) -> None:
        """Configure falhas determinísticas sem acessar serviços externos."""
        self.failure = failure
        self.final_state = WorkflowJobState.RUNNING
        self.cancel_requested = False
        self.drain_requested = False
        self.cleanup_waited = False
        self.fail_cleanup = fail_cleanup

    def ensure_step(self, step: FailurePoint) -> None:
        """Execute uma etapa ou injete a falha selecionada."""
        if self.failure is step:
            raise WorkflowExecutionError(step)

    def request_drain(self) -> None:
        """Solicite drain."""
        self.drain_requested = True
        self.final_state = WorkflowJobState.DRAINING

    def request_cancel(self) -> None:
        """Solicite cancelamento."""
        self.cancel_requested = True
        self.final_state = WorkflowJobState.CANCELLED
        if self.fail_cleanup:
            raise WorkflowCleanupError

    def wait_terminal(self) -> None:
        """Aguarde um estado terminal."""
        self.cleanup_waited = True
        if self.final_state is WorkflowJobState.DRAINING:
            self.final_state = WorkflowJobState.DRAINED


def run_guarded_workflow(port: WorkflowPort) -> WorkflowResult:
    """Executa o caminho feliz e garante terminalidade antes de propagar falhas."""
    try:
        port.ensure_step(FailurePoint.PRODUCER)
        port.ensure_step(FailurePoint.STAGE)
        port.ensure_step(FailurePoint.RAW_STALE)
        port.request_drain()
        port.wait_terminal()
        port.ensure_step(FailurePoint.MERGE)
        port.ensure_step(FailurePoint.BACKLOG)
    except WorkflowExecutionError:
        try:
            if not port.final_state.is_terminal:
                port.request_cancel()
            port.wait_terminal()
        except WorkflowCleanupError as cleanup_error:
            _ = cleanup_error
        raise
    return WorkflowResult(success=True, final_state=port.final_state)
