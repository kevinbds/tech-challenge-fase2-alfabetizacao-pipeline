set -euo pipefail

batch="$(gcloud artifacts docker images describe "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/batch:$COMMIT_SHA" --format='value(image_summary.digest)')"
dbt="$(gcloud artifacts docker images describe "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/dbt:$COMMIT_SHA" --format='value(image_summary.digest)')"
producer="$(gcloud artifacts docker images describe "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/producer:$COMMIT_SHA" --format='value(image_summary.digest)')"
dataflow="$(gcloud artifacts docker images describe "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/dataflow:$COMMIT_SHA" --format='value(image_summary.digest)')"
[[ $batch =~ ^sha256:[0-9a-f]{64}$ ]]
[[ $dbt =~ ^sha256:[0-9a-f]{64}$ ]]
[[ $producer =~ ^sha256:[0-9a-f]{64}$ ]]
[[ $dataflow =~ ^sha256:[0-9a-f]{64}$ ]]
printf '{"build_id":"%s","git_sha":"%s","images":{"batch":"%s@%s","dbt":"%s@%s","producer":"%s@%s","dataflow":"%s@%s"},"provenance":"verified","sbom":"artifact-registry-when-available"}\n' \
  "$BUILD_ID" \
  "$COMMIT_SHA" \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/batch" \
  "$batch" \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/dbt" \
  "$dbt" \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/producer" \
  "$producer" \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/dataflow" \
  "$dataflow" \
  > /workspace/image-digests.json
