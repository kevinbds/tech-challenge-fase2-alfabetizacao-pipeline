import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, override

BEAM_DIRECT_PROGRAM: Final = """
import json
import sys
from pathlib import Path
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions

source = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
prefix = sys.argv[2]
with beam.Pipeline(options=PipelineOptions(["--runner=DirectRunner", "--streaming"])) as pipeline:
    (
        pipeline
        | "CreateMessages" >> beam.Create(source)
        | "ParseBoundary" >> beam.Map(lambda item: json.loads(item)["message_id"])
        | "PhysicalDedup" >> beam.Distinct()
        | "WriteRawIds" >> beam.io.WriteToText(prefix, num_shards=1)
    )
"""


@dataclass(frozen=True, slots=True)
class BeamExecutionError(RuntimeError):
    """Indica falha do processo isolado do DirectRunner."""

    return_code: int

    @override
    def __str__(self) -> str:
        """Retorna somente o código, sem copiar dados processados."""
        return f"DirectRunner encerrou com código {self.return_code}"


def run_direct(messages: tuple[str, ...], output_prefix: Path) -> None:
    """Executa deduplicação física com Beam 2.75 em modo streaming."""
    input_path = output_prefix.parent / "beam-input.jsonl"
    _ = input_path.write_text("\n".join(messages) + "\n", encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - executável e programa são constantes locais
        [sys.executable, "-c", BEAM_DIRECT_PROGRAM, str(input_path), str(output_prefix)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    input_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise BeamExecutionError(return_code=completed.returncode)
