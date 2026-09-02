#!/usr/bin/env bash
set -euo pipefail

is_available_commit() {
  local revision="$1"
  [[ "$revision" =~ ^[0-9a-f]{40}$ ]] || return 1
  [[ "$revision" != "0000000000000000000000000000000000000000" ]] || return 1
  git cat-file -e "${revision}^{commit}" 2>/dev/null
}

head_sha="${GITHUB_SHA:-HEAD}"
scan_range="HEAD"

case "${GITHUB_EVENT_NAME:-}" in
  pull_request)
    if is_available_commit "${GITLEAKS_PR_BASE_SHA:-}"; then
      scan_range="${GITLEAKS_PR_BASE_SHA}..${head_sha}"
    fi
    ;;
  push)
    if is_available_commit "${GITLEAKS_PUSH_BEFORE:-}"; then
      scan_range="${GITLEAKS_PUSH_BEFORE}..${head_sha}"
    fi
    ;;
esac

scanner="${GITLEAKS_SCANNER:-scripts/gitleaks-scan.sh}"
exec "${scanner}" git --no-banner --redact "--log-opts=${scan_range}"
