from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeGuard, final, override

import apache_beam as beam
from apache_beam.pvalue import PBegin, PCollection, PDone, PValue

if TYPE_CHECKING:
    from collections.abc import Callable

    from apache_beam.transforms.ptransform import PTransform


class _PipelineResult(Protocol):
    def wait_until_finish(self) -> None: ...


class _BeamTransformError(TypeError): ...


@final
class _MapDoFn[InputT, OutputT](beam.DoFn):
    def __init__(self, function: Callable[[InputT], OutputT]) -> None:
        object.__init__(self)
        self._function: Callable[[InputT], OutputT] = function

    @override
    def process(self, element: InputT) -> list[OutputT]:
        return [self._function(element)]


def _is_collection_output[InputT, OutputT](
    value: PValue,
    _: PTransform[InputT, PCollection[OutputT]],
) -> TypeGuard[PCollection[OutputT]]:
    return isinstance(value, PCollection)


def map_transform[InputT, OutputT](
    function: Callable[[InputT], OutputT],
) -> PTransform[PCollection[InputT], PCollection[OutputT]]:
    """Create a Beam map transform with concrete input and output types."""
    return beam.ParDo(_MapDoFn(function))


def create_transform[RowT](
    values: list[RowT],
) -> PTransform[PBegin, PCollection[RowT]]:
    """Create a typed in-memory Beam source."""
    return beam.Create(values)


def apply_collection_transform[InputT, OutputT](
    source: PCollection[InputT],
    label: str,
    transform: PTransform[PCollection[InputT], PCollection[OutputT]],
) -> PCollection[OutputT]:
    """Apply one transform while preserving its element type contract."""
    result = source | label >> transform
    if not _is_collection_output(result, transform):
        raise _BeamTransformError
    return result


def create_collection[RowT](
    pipeline: beam.Pipeline,
    label: str,
    transform: PTransform[PBegin, PCollection[RowT]],
) -> PCollection[RowT]:
    """Apply a typed source transform to a pipeline root."""
    result = PBegin(pipeline) | label >> transform
    if not _is_collection_output(result, transform):
        raise _BeamTransformError
    return result


def write_collection[RowT](
    source: PCollection[RowT],
    label: str,
    transform: PTransform[PCollection[RowT], PDone],
) -> None:
    """Apply a terminal Beam sink."""
    result: PValue = source | label >> transform
    _ = result


def wait_for_result(result: _PipelineResult) -> None:
    """Wait through the stable subset of Beam's result interface."""
    result.wait_until_finish()
