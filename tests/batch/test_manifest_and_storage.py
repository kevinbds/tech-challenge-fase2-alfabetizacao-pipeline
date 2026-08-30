from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from alfabetizacao_pipeline.batch.errors import ImmutableObjectExistsError
from alfabetizacao_pipeline.batch.fakes import InMemoryObjectStore
from alfabetizacao_pipeline.batch.models import (
    BatchManifest,
    BatchStatus,
    BronzeObject,
    SourceIdentity,
)


def test_generation_precondition_prevents_overwrite_when_writing() -> None:
    # Given: an immutable object already stored at one URI
    store = InMemoryObjectStore()
    _ = store.write_immutable("gs://bronze/uf/ano=2024/run=a/data.parquet", b"first")
    # When: another writer targets the same URI
    # Then: generation-match zero rejects the overwrite
    with pytest.raises(ImmutableObjectExistsError):
        _ = store.write_immutable("gs://bronze/uf/ano=2024/run=a/data.parquet", b"second")


def test_manifest_rejects_student_identifier_when_parsed() -> None:
    # Given: external manifest metadata containing prohibited PII text
    payload = """{
      "run_id":"run-1","source":"uf","year":2024,"status":"completed",
      "source_identity":{"location":"US","etag":"id_aluno=secret"},
      "row_count":1,"fingerprint":"fp","query_hash":"q","schema_hash":"s",
      "bronze_objects":[],"started_at":"2025-01-01T00:00:00Z",
      "completed_at":"2025-01-01T00:01:00Z","git_sha":"abc",
      "image_digest":"sha256:abc"
    }"""
    # When/Then: parsing rejects it before persistence
    with pytest.raises(ValidationError):
        _ = BatchManifest.model_validate_json(payload)


def test_completed_manifest_records_object_integrity_when_created() -> None:
    # Given: a completed immutable Bronze object
    bronze = BronzeObject(
        uri="gs://bronze/uf/data.parquet", generation=1, crc32c="AAAAAA==", size_bytes=9
    )
    # When: its manifest is constructed
    manifest = BatchManifest(
        run_id="run-1",
        source="uf",
        year=2024,
        status=BatchStatus.COMPLETED,
        source_identity=SourceIdentity(location="US", modified_at=None, etag="etag"),
        row_count=1,
        fingerprint="fp",
        query_hash="q",
        schema_hash="s",
        bronze_objects=(bronze,),
        started_at=datetime(2025, 1, 1, tzinfo=UTC),
        completed_at=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
        git_sha="abc",
        image_digest="sha256:abc",
    )
    # Then: provenance is serializable without student identifiers
    assert manifest.bronze_objects[0].generation == 1
    assert "id_aluno" not in manifest.model_dump_json()
