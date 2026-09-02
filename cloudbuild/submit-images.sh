set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID é obrigatório}"
: "${GCP_REGION:?GCP_REGION é obrigatório}"
: "${GCP_CLOUD_BUILD_SERVICE_ACCOUNT:?GCP_CLOUD_BUILD_SERVICE_ACCOUNT é obrigatório}"
: "${GCP_ARTIFACT_REPOSITORY:?GCP_ARTIFACT_REPOSITORY é obrigatório}"
: "${GCP_ARTIFACT_BUCKET:?GCP_ARTIFACT_BUCKET é obrigatório}"
: "${GITHUB_SHA:?GITHUB_SHA é obrigatório}"

build_id="$(gcloud builds submit \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --config=cloudbuild/build-images.yml \
  --service-account="projects/$GCP_PROJECT_ID/serviceAccounts/$GCP_CLOUD_BUILD_SERVICE_ACCOUNT" \
  --gcs-source-staging-dir="gs://$GCP_ARTIFACT_BUCKET/sources" \
  --suppress-logs \
  --format='value(id)' \
  --substitutions="_REGION=$GCP_REGION,_REPOSITORY=$GCP_ARTIFACT_REPOSITORY,_ARTIFACT_BUCKET=$GCP_ARTIFACT_BUCKET,COMMIT_SHA=$GITHUB_SHA" \
  .)"

digest_manifest="$(gcloud builds describe "$build_id" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --format=json | bash cloudbuild/capture-digests.sh)"

batch_image="$(jq -er '.images.batch' <<<"$digest_manifest")"
dbt_image="$(jq -er '.images.dbt' <<<"$digest_manifest")"
producer_image="$(jq -er '.images.producer' <<<"$digest_manifest")"
dataflow_template_image="$(jq -er '.images.dataflow_template' <<<"$digest_manifest")"
dataflow_sdk_image="$(jq -er '.images.dataflow_sdk' <<<"$digest_manifest")"

verification_build_id="$(gcloud builds submit \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --config=cloudbuild/verify-images.yml \
  --no-source \
  --service-account="projects/$GCP_PROJECT_ID/serviceAccounts/$GCP_CLOUD_BUILD_SERVICE_ACCOUNT" \
  --suppress-logs \
  --format='value(id)' \
  --substitutions="_BATCH_IMAGE=$batch_image,_DBT_IMAGE=$dbt_image,_PRODUCER_IMAGE=$producer_image,_DATAFLOW_TEMPLATE_IMAGE=$dataflow_template_image,_DATAFLOW_SDK_IMAGE=$dataflow_sdk_image,_ARTIFACT_BUCKET=$GCP_ARTIFACT_BUCKET,_GIT_SHA=$GITHUB_SHA")"

verification_status="$(gcloud builds describe "$verification_build_id" \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --format='value(status)')"
[[ $verification_status == SUCCESS ]]

runtime_smoke_uri="gs://$GCP_ARTIFACT_BUCKET/runtime-smoke/$verification_build_id/runtime-smoke.json"
jq -ce \
  --arg verification_build_id "$verification_build_id" \
  --arg runtime_smoke_uri "$runtime_smoke_uri" \
  '. + {verification_build_id: $verification_build_id, runtime_smoke_uri: $runtime_smoke_uri}' \
  <<<"$digest_manifest"
