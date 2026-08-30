from dataclasses import dataclass
from typing import override


@dataclass(frozen=True, slots=True)
class CostLimitExceededError(Exception):
    """Dry-run estimate exceeds the authorized billing ceiling."""

    estimated_bytes: int
    maximum_bytes_billed: int

    @override
    def __str__(self) -> str:
        """Render the estimate and cap without query contents."""
        return (
            f"consulta estimada em {self.estimated_bytes} bytes excede o limite "
            f"de {self.maximum_bytes_billed} bytes"
        )


@dataclass(frozen=True, slots=True)
class ImmutableObjectExistsError(Exception):
    """An immutable object path already has generation one."""

    uri: str

    @override
    def __str__(self) -> str:
        """Render the conflicting URI."""
        return f"objeto imutável já existe: {self.uri}"


@dataclass(frozen=True, slots=True)
class SchemaDriftError(Exception):
    """Runtime source schema is incompatible with its pinned contract."""

    source: str

    @override
    def __str__(self) -> str:
        """Render the source with incompatible drift."""
        return f"schema incompatível para a fonte {self.source}"


@dataclass(frozen=True, slots=True)
class IncompleteRunError(Exception):
    """A release operation received an incomplete manifest."""

    run_id: str

    @override
    def __str__(self) -> str:
        """Render the incomplete run identifier."""
        return f"run incompleto não pode ser promovido: {self.run_id}"


@dataclass(frozen=True, slots=True)
class LandingSchemaError(Exception):
    """Landing Parquet columns differ from the pinned source contract."""

    source: str

    @override
    def __str__(self) -> str:
        """Render the source whose landing schema differs."""
        return f"landing com schema incompatível para {self.source}"


@dataclass(frozen=True, slots=True)
class UnsupportedSchemaTypeError(Exception):
    """Reference schema contains an unsupported BigQuery type."""

    data_type: str

    @override
    def __str__(self) -> str:
        """Render the unsupported source type."""
        return f"tipo BigQuery não suportado: {self.data_type}"


@dataclass(frozen=True, slots=True)
class InvalidTableIdentifierError(Exception):
    """BigQuery table identifier fails the strict project.dataset.table pattern."""

    table: str

    @override
    def __str__(self) -> str:
        """Render the rejected identifier."""
        return f"identificador BigQuery inválido: {self.table}"


@dataclass(frozen=True, slots=True)
class SourceInspectionRequiredError(Exception):
    """A query was attempted before discovering its runtime location."""

    source: str

    @override
    def __str__(self) -> str:
        """Render the source that still requires inspection."""
        return f"inspeção de localização obrigatória para {self.source}"


@dataclass(frozen=True, slots=True)
class ManifestConflictError(Exception):
    """A concurrent writer used the same checkpoint URI with different content."""

    uri: str

    @override
    def __str__(self) -> str:
        """Render the immutable checkpoint conflict."""
        return f"checkpoint concorrente diverge do conteúdo persistido: {self.uri}"


@dataclass(frozen=True, slots=True)
class StaleObjectGenerationError(Exception):
    """An object changed after its immutable version was selected."""

    uri: str

    @override
    def __str__(self) -> str:
        return f"geração do objeto mudou durante a leitura: {self.uri}"
