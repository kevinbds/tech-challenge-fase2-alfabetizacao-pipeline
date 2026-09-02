set -euo pipefail

jq -ce -f cloudbuild/capture-digests.jq
