set -euo pipefail

: "${BATCH_IMAGE:?BATCH_IMAGE é obrigatório}"

workspace="${WORKSPACE:-/workspace}"
docker_bin="${DOCKER_BIN:-docker}"
output_root="$workspace/reference-schemas"
index="$output_root/index.tsv"
sources=(
  uf
  meta_alfabetizacao_brasil
  meta_alfabetizacao_uf
  meta_alfabetizacao_municipio
  municipio
  alunos
)

mkdir -p "$output_root"
: > "$index"

for source in "${sources[@]}"; do
  output="$output_root/$source/schema.parquet"
  descriptor="$("$docker_bin" run --rm --user 0:0 --volume "$workspace:/workspace" --entrypoint alfabetizacao "$BATCH_IMAGE" schema-reference build-reference --source "$source" --output "/workspace/reference-schemas/$source/schema.parquet")"
  schema_hash="$(printf '%s' "$descriptor" | sed -n 's/.*"schema_hash":"\([0-9a-f]\{64\}\)".*/\1/p')"
  [[ $schema_hash =~ ^[0-9a-f]{64}$ ]]
  [[ -f $output ]]
  printf '%s\t%s\n' "$source" "$schema_hash" >> "$index"
done
