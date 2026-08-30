from pathlib import Path

from typer.testing import CliRunner

from alfabetizacao_pipeline.schema_reference.commands import app
from alfabetizacao_pipeline.schema_reference.models import ReferenceSchemaDescriptor


def test_schema_command_builds_parseable_reference_artifact(tmp_path: Path) -> None:
    # Given: a target file in an isolated directory
    output = tmp_path / "reference.parquet"
    # When: the public schema command runs
    result = CliRunner().invoke(
        app,
        ["build-reference", "--source", "uf", "--output", str(output)],
    )
    descriptor = ReferenceSchemaDescriptor.model_validate_json(result.stdout)
    # Then: both JSON descriptor and Parquet artifact exist
    assert result.exit_code == 0
    assert descriptor.local_path == output
    assert output.is_file()
