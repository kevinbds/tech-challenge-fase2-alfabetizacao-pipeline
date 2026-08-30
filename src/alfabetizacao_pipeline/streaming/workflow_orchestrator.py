from dataclasses import dataclass
from enum import StrEnum, unique
from typing import ClassVar, Final, Protocol, override

DISCOVERY_PAGE_SIZE: Final = 100
MAX_DISCOVERY_PAGES: Final = 100


@unique
class FailurePoint(StrEnum):
    """Etapas em que o simulador pode injetar uma falha determinística."""

    NONE = "none"
    LAUNCH_AFTER_CREATE = "launch_after_create"
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


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Resultado local de uma varredura paginada bounded."""

    found: bool
    pages_scanned: int
    repeated_token_detected: bool


def simulate_paginated_discovery(
    active_jobs_before_target: int,
    *,
    target_matches: bool,
    repeated_page_token: bool,
) -> DiscoveryResult:
    """Simule paginação, correlação exata e proteção contra token repetido."""
    target_page = active_jobs_before_target // DISCOVERY_PAGE_SIZE + 1
    if repeated_page_token and target_page > 1:
        return DiscoveryResult(found=False, pages_scanned=2, repeated_token_detected=True)
    pages_scanned = min(target_page, MAX_DISCOVERY_PAGES)
    return DiscoveryResult(
        found=target_matches and target_page <= MAX_DISCOVERY_PAGES,
        pages_scanned=pages_scanned,
        repeated_token_detected=False,
    )


class WorkflowPort(Protocol):
    """Porta mínima para testar cleanup sem chamar a nuvem."""

    @property
    def final_state(self) -> WorkflowJobState:
        """Exponha o estado atual."""
        ...

    @property
    def job_id_known(self) -> bool:
        """Exponha se o launch retornou o identificador."""
        ...

    def launch(self) -> None:
        """Execute o launch guardado."""
        ...

    def discover_job(self) -> None:
        """Resolva um launch ambíguo por correlação exata."""
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
        "discovery_requested",
        "drain_requested",
        "fail_cleanup",
        "failure",
        "final_state",
        "job_id_known",
    )
    failure: FailurePoint
    final_state: WorkflowJobState
    cancel_requested: bool
    drain_requested: bool
    discovery_requested: bool
    cleanup_waited: bool
    fail_cleanup: bool
    job_id_known: bool

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
        self.discovery_requested = False
        self.cleanup_waited = False
        self.fail_cleanup = fail_cleanup
        self.job_id_known = True

    def launch(self) -> None:
        """Simule inclusive timeout ocorrido após a criação remota."""
        if self.failure is FailurePoint.LAUNCH_AFTER_CREATE:
            self.job_id_known = False
            raise WorkflowExecutionError(FailurePoint.LAUNCH_AFTER_CREATE)

    def discover_job(self) -> None:
        """Registre a recuperação do job criado sem resposta completa."""
        self.discovery_requested = True
        if self.fail_cleanup:
            raise WorkflowCleanupError
        self.job_id_known = True

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
        port.launch()
        port.ensure_step(FailurePoint.PRODUCER)
        port.ensure_step(FailurePoint.STAGE)
        port.ensure_step(FailurePoint.RAW_STALE)
        port.request_drain()
        port.wait_terminal()
        port.ensure_step(FailurePoint.MERGE)
        port.ensure_step(FailurePoint.BACKLOG)
    except WorkflowExecutionError:
        try:
            if not port.job_id_known:
                port.discover_job()
            if not port.final_state.is_terminal:
                port.request_cancel()
            port.wait_terminal()
        except WorkflowCleanupError as cleanup_error:
            _ = cleanup_error
        raise
    return WorkflowResult(success=True, final_state=port.final_state)
