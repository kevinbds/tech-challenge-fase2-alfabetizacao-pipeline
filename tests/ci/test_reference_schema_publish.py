import os
import subprocess
from pathlib import Path

SOURCES = (
    "uf",
    "meta_alfabetizacao_brasil",
    "meta_alfabetizacao_uf",
    "meta_alfabetizacao_municipio",
    "municipio",
    "alunos",
)
SCHEMA_HASH = "a" * 64
GIT_SHA = "b" * 40


def _bash() -> str:
    return r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"


def test_schema_publish_when_cloudbuild_helpers_run_with_fake_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    bin_dir = tmp_path / "bin"
    workspace.mkdir()
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    gcloud = bin_dir / "gcloud"
    _ = docker.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
source=''
output=''
workspace=''
while (($#)); do
  case "$1" in
    --volume) workspace="${2%:/workspace}"; shift 2 ;;
    --source) source="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    *) shift ;;
  esac
done
output="$workspace/${output#/workspace/}"
mkdir -p "$(dirname "$output")"
: > "$output"
printf '{"source":"%s","schema_hash":"%s"}\\n' "$source" "${SCHEMA_HASH}"
""".replace("${SCHEMA_HASH}", SCHEMA_HASH),
        encoding="utf-8",
    )
    _ = gcloud.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$GCLOUD_CALLS"
store="$GCLOUD_STORE"
to_path() {
  printf '%s/%s' "$store" "${1#gs://}"
}
if [[ "$1 $2 $3" == 'storage objects describe' ]]; then
  test -f "$(to_path "$4")"
  exit
fi
if [[ "$1 $2" == 'storage cp' ]]; then
  shift 2
  if [[ $1 == '--if-generation-match=0' ]]; then
    shift
  fi
  source="$1"
  destination="$2"
  if [[ $source == gs://* ]]; then
    cp "$(to_path "$source")" "$destination"
  else
    target="$(to_path "$destination")"
    mkdir -p "$(dirname "$target")"
    test ! -e "$target"
    cp "$source" "$target"
  fi
fi
""",
        encoding="utf-8",
    )
    _ = docker.chmod(0o755)
    _ = gcloud.chmod(0o755)
    calls = tmp_path / "gcloud-calls.txt"
    store = tmp_path / "gcs"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "WORKSPACE": str(workspace),
        "BATCH_IMAGE": "batch:test",
        "DOCKER_BIN": str(docker),
        "ARTIFACT_BUCKET": "test-artifacts",
        "COMMIT_SHA": GIT_SHA,
        "GCLOUD_CALLS": str(calls),
        "GCLOUD_STORE": str(store),
    }

    _ = subprocess.run(
        [_bash(), "cloudbuild/build-reference-schemas.sh"],
        check=True,
        env=environment,
    )
    result = subprocess.run(
        [_bash(), "cloudbuild/publish-reference-schemas.sh"],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    _ = subprocess.run(
        [_bash(), "cloudbuild/build-reference-schemas.sh"],
        check=True,
        env=environment,
    )
    rerun = subprocess.run(
        [_bash(), "cloudbuild/publish-reference-schemas.sh"],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    manifest = (workspace / "reference-schema-uris.tfvars.json").read_text(encoding="utf-8")
    assert result.stdout.strip() == manifest.strip()
    assert rerun.stdout.strip() == manifest.strip()
    assert manifest.count("schema.parquet") == len(SOURCES)
    assert all(
        f'"{source}":"gs://test-artifacts/reference/{source}/{SCHEMA_HASH}/schema.parquet"'
        in manifest
        for source in SOURCES
    )
    assert calls.read_text(encoding="utf-8").count("--if-generation-match=0") == len(SOURCES) + 1
