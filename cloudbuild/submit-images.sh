set -euo pipefail

gcloud builds submit \
  --project="$GCP_PROJECT_ID" \
  --region="$GCP_REGION" \
  --config=cloudbuild/build-images.yml \
  --service-account="$GCP_CLOUD_BUILD_SERVICE_ACCOUNT" \
  --substitutions="_REGION=$GCP_REGION,_REPOSITORY=$GCP_ARTIFACT_REPOSITORY,_SERVICE_ACCOUNT=$GCP_CLOUD_BUILD_SERVICE_ACCOUNT,_ARTIFACT_BUCKET=$GCP_ARTIFACT_BUCKET,COMMIT_SHA=$GITHUB_SHA" \
  .
