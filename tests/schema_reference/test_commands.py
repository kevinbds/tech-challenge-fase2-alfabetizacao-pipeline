from pathlib import Path

from typer.testing import CliRunner

from alfabetizacao_pipeline.schema_reference.commands import app
from alfabetizacao_pipeline.schema_reference.models import ReferenceSchemaDescriptor


def test_schema_command_builds_parseable_reference_artifact(tmp_path: Path) -> None:
    output = tmp_path / "reference.parquet"
    result = CliRunner().invoke(
        app,
        ["build-reference", "--source", "uf", "--output", str(output)],
    )
    descriptor = ReferenceSchemaDescriptor.model_validate_json(result.stdout)
    assert result.exit_code == 0
    assert descriptor.local_path == output
    assert "gs://" not in result.stdout
    assert output.is_file()
