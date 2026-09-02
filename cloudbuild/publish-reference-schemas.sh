set -euo pipefail

: "${ARTIFACT_BUCKET:?ARTIFACT_BUCKET é obrigatório}"
: "${COMMIT_SHA:?COMMIT_SHA é obrigatório}"

[[ $COMMIT_SHA =~ ^[0-9a-f]{40}$ ]]

workspace="${WORKSPACE:-/workspace}"
output_root="$workspace/reference-schemas"
index="$output_root/index.tsv"
manifest="$workspace/reference-schema-uris.tfvars.json"
sources=(
  uf
  meta_alfabetizacao_brasil
  meta_alfabetizacao_uf
  meta_alfabetizacao_municipio
  municipio
  alunos
)

upload_immutable() {
  local source="$1"
  local destination="$2"
  local existing="$source.existing"

  if gcloud storage objects describe "$destination" --format='value(generation)' >/dev/null 2>&1; then
    gcloud storage cp "$destination" "$existing"
    cmp --silent "$source" "$existing"
    rm -f "$existing"
    return
  fi

  if gcloud storage cp --if-generation-match=0 "$source" "$destination"; then
    return
  fi

  gcloud storage objects describe "$destination" --format='value(generation)' >/dev/null
  gcloud storage cp "$destination" "$existing"
  cmp --silent "$source" "$existing"
  rm -f "$existing"
}

[[ -f $index ]]
[[ $(wc -l < "$index") -eq ${#sources[@]} ]]

printf '{"release_git_sha":"%s","reference_schema_uris":{' "$COMMIT_SHA" > "$manifest"
separator=""
for source in "${sources[@]}"; do
  schema_hash="$(awk -F '\t' -v expected="$source" '$1 == expected {print $2}' "$index")"
  [[ $schema_hash =~ ^[0-9a-f]{64}$ ]]
  artifact="$output_root/$source/schema.parquet"
  uri="gs://$ARTIFACT_BUCKET/reference/$source/$schema_hash/schema.parquet"
  [[ -f $artifact ]]
  upload_immutable "$artifact" "$uri"
  printf '%s"%s":"%s"' "$separator" "$source" "$uri" >> "$manifest"
  separator=","
done
printf '}}\n' >> "$manifest"

manifest_uri="gs://$ARTIFACT_BUCKET/reference-manifests/$COMMIT_SHA.json"
upload_immutable "$manifest" "$manifest_uri"
cat "$manifest"
