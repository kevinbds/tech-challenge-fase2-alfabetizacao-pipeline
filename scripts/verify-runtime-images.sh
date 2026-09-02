#!/usr/bin/env bash
set -uo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly CONTRACT_PATH="${SCRIPT_DIR}/../containers/smoke-contract.json"
readonly REQUIRED_IMAGES=(batch dbt producer dataflow_template dataflow_sdk)
readonly DIGEST_PATTERN='@sha256:[a-f0-9]{64}$'

allow_local_tags=false
docker_bin=docker
git_sha="$(git rev-parse --verify HEAD 2>/dev/null || true)"
pull_images=false
report_path=""
python_bin="${PYTHON_BIN:-python}"
declare -A references=()
declare -a result_rows=()

usage() {
  cat <<'EOF'
Usage: scripts/verify-runtime-images.sh --batch REF --dbt REF --producer REF --dataflow-template REF --dataflow-sdk REF [options]

Options:
  --allow-local-tags  permit tags only for an explicit local development smoke
  --docker PATH       Docker executable to invoke (default: docker)
  --git-sha SHA       40-character source revision recorded in the report
  --pull              pull each immutable reference before the smoke
  --report PATH       write the JSON report to PATH (also printed to stdout)
EOF
}

fail() {
  printf '%s\n' "$1" >&2
  exit 2
}

require_value() {
  [[ $# -eq 2 && -n $2 ]] || fail "missing value for $1"
}

contract_scalar() {
  "$python_bin" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$CONTRACT_PATH" "$1"
}

contract_entrypoint() {
  "$python_bin" -c 'import json, sys; print(json.dumps(json.load(open(sys.argv[1], encoding="utf-8"))["images"][sys.argv[2]]["entrypoint"], separators=(",", ":")))' "$CONTRACT_PATH" "$1"
}

contract_check_count() {
  "$python_bin" -c 'import json, sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))["images"][sys.argv[2]]["checks"]))' "$CONTRACT_PATH" "$1"
}

contract_check_scalar() {
  "$python_bin" -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["images"][sys.argv[2]]["checks"][int(sys.argv[3])].get(sys.argv[4], ""))' "$CONTRACT_PATH" "$1" "$2" "$3"
}

contract_check_arguments() {
  "$python_bin" -c 'import json, sys; [sys.stdout.buffer.write(value.encode("utf-8") + b"\0") for value in json.load(open(sys.argv[1], encoding="utf-8"))["images"][sys.argv[2]]["checks"][int(sys.argv[3])]["arguments"]]' "$CONTRACT_PATH" "$1" "$2"
}

record() {
  local image_name=$1 check_name=$2 status=$3 exit_code=$4
  result_rows+=("${image_name}"$'\t'"${references[$image_name]}"$'\t'"${check_name}"$'\t'"${status}"$'\t'"${exit_code}")
}

run_check() {
  local image_name=$1 check_index=$2
  local check_name expected_exit docker_entrypoint exit_code status
  local -a arguments command

  check_name="$(contract_check_scalar "$image_name" "$check_index" name)"
  expected_exit="$(contract_check_scalar "$image_name" "$check_index" expected_exit)"
  docker_entrypoint="$(contract_check_scalar "$image_name" "$check_index" docker_entrypoint)"
  mapfile -d '' -t arguments < <(contract_check_arguments "$image_name" "$check_index")
  command=("$docker_bin" run --rm)
  if [[ -n $docker_entrypoint ]]; then
    command+=(--entrypoint "$docker_entrypoint")
  fi
  command+=("${references[$image_name]}" "${arguments[@]}")

  timeout --foreground "${timeout_seconds}s" "${command[@]}" >&2
  exit_code=$?
  if [[ $exit_code -eq $expected_exit ]]; then
    status=passed
  else
    status=failed
  fi
  record "$image_name" "$check_name" "$status" "$exit_code"
}

write_report() {
  local overall=passed row row_status
  for row in "${result_rows[@]}"; do
    IFS=$'\t' read -r _ _ _ row_status _ <<<"$row"
    [[ $row_status == passed ]] || overall=failed
  done
  printf '%s\n' "${result_rows[@]}" | "$python_bin" -c '
import json
import sys
from collections import defaultdict

images = defaultdict(lambda: {"reference": "", "status": "passed", "checks": []})
for line in sys.stdin:
    image, reference, check, status, exit_code = line.rstrip("\n").split("\t")
    current = images[image]
    current["reference"] = reference
    current["checks"].append({"name": check, "status": status, "exit_code": int(exit_code)})
    if status != "passed":
        current["status"] = "failed"
print(json.dumps({
    "contract_version": sys.argv[1],
    "git_sha": sys.argv[2],
    "approval_mode": sys.argv[3] == "true",
    "overall": sys.argv[4],
    "images": dict(images),
}, sort_keys=True))
' "$(contract_scalar version)" "$git_sha" "$([ "$allow_local_tags" = false ] && printf true || printf false)" "$overall"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-local-tags) allow_local_tags=true ;;
    --batch|--dbt|--producer)
      require_value "$1" "${2:-}"
      references["${1#--}"]=$2
      shift
      ;;
    --dataflow-template|--dataflow-sdk)
      require_value "$1" "${2:-}"
      references["dataflow_${1#--dataflow-}"]=$2
      shift
      ;;
    --docker)
      require_value "$1" "${2:-}"
      docker_bin=$2
      shift
      ;;
    --git-sha)
      require_value "$1" "${2:-}"
      git_sha=$2
      shift
      ;;
    --pull) pull_images=true ;;
    --report)
      require_value "$1" "${2:-}"
      report_path=$2
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *) fail "unknown option: $1" ;;
  esac
  shift
done

command -v "$python_bin" >/dev/null 2>&1 || fail "Python is required to read ${CONTRACT_PATH}"
[[ -f $CONTRACT_PATH ]] || fail "missing smoke contract: ${CONTRACT_PATH}"
[[ $git_sha =~ ^[0-9a-f]{40}$ ]] || fail "--git-sha must be a 40-character lowercase SHA"
[[ "$(contract_scalar version)" == 2.0 ]] || fail "unsupported smoke contract version"
[[ "$(contract_scalar digest_required)" == True ]] || fail "smoke contract must require immutable digests"
readonly timeout_seconds="$(contract_scalar timeout_seconds)"
[[ $timeout_seconds =~ ^[1-9][0-9]*$ ]] || fail "smoke contract timeout_seconds must be positive"

for image_name in "${REQUIRED_IMAGES[@]}"; do
  cli_name="${image_name//_/-}"
  reference="${references[$image_name]:-}"
  [[ -n $reference ]] || fail "missing --${cli_name} reference"
  if [[ $allow_local_tags == false && ! $reference =~ $DIGEST_PATTERN ]]; then
    fail "--${cli_name} must be an immutable digest reference ending in @sha256:<64 lowercase hex>"
  fi
done

for image_name in "${REQUIRED_IMAGES[@]}"; do
  if [[ $pull_images == true ]]; then
    "$docker_bin" pull "${references[$image_name]}" >&2
    pull_exit=$?
    if [[ $pull_exit -ne 0 ]]; then
      record "$image_name" pull failed "$pull_exit"
      continue
    fi
    record "$image_name" pull passed "$pull_exit"
  fi
  if [[ $image_name == dataflow_template || $image_name == dataflow_sdk ]]; then
    actual_entrypoint="$("$docker_bin" inspect --format '{{json .Config.Entrypoint}}' "${references[$image_name]}")"
    expected_entrypoint="$(contract_entrypoint "$image_name")"
    if [[ $actual_entrypoint == "$expected_entrypoint" ]]; then
      record "$image_name" entrypoint passed 0
    else
      record "$image_name" entrypoint failed 1
      continue
    fi
  fi
  check_count="$(contract_check_count "$image_name")"
  for ((check_index = 0; check_index < check_count; check_index += 1)); do
    run_check "$image_name" "$check_index"
  done
done

if ! report="$(write_report)"; then
  fail "could not generate smoke report"
fi
if [[ -n $report_path ]]; then
  printf '%s\n' "$report" >"$report_path" || fail "could not write report: $report_path"
fi
printf '%s\n' "$report"
if [[ $report == *'"overall": "failed"'* ]]; then
  exit 1
fi
