#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/bin:/mingw64/bin:${PATH:-}"

version="8.30.1"
case "$(uname -s)" in
  Linux*)
    package="gitleaks_${version}_linux_x64.tar.gz"
    checksum="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
    executable="gitleaks"
    ;;
  MINGW*|MSYS*)
    package="gitleaks_${version}_windows_x64.zip"
    checksum="d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"
    executable="gitleaks.exe"
    ;;
  *)
    printf 'Unsupported operating system: %s\n' "$(uname -s)" >&2
    exit 2
    ;;
esac

temp_dir="$(mktemp -d)"
archive="${temp_dir}/${package}"
binary="${temp_dir}/${executable}"
cleanup() {
  rm -f -- "${archive}" "${binary}"
  rmdir -- "${temp_dir}"
}
trap cleanup EXIT

curl -fsSLo "${archive}" "https://github.com/gitleaks/gitleaks/releases/download/v${version}/${package}"
printf '%s  %s\n' "${checksum}" "${archive}" | sha256sum --check --status
case "${package}" in
  *.tar.gz) tar -xzf "${archive}" -C "${temp_dir}" "${executable}" ;;
  *.zip) unzip -q "${archive}" "${executable}" -d "${temp_dir}" ;;
esac
"${binary}" "$@"
