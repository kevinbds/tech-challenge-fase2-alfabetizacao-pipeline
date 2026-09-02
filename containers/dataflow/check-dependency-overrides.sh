#!/bin/sh
set -eu

set +e
actual="$(python -m pip check 2>&1)"
status=$?
set -e

if [ "$status" -ne 1 ]; then
    printf '%s\n' "expected exactly the documented Apache Beam dependency conflicts" >&2
    exit 1
fi

actual="$(printf '%s\n' "$actual" | LC_ALL=C sort)"
expected="$(printf '%s\n' \
    'apache-beam 2.75.0 has requirement cryptography<48.0.0,>=39.0.0, but you have cryptography 50.0.1.' \
    'apache-beam 2.75.0 has requirement httplib2<0.32.0,>=0.8, but you have httplib2 0.32.0.' \
    | LC_ALL=C sort)"

if [ "$actual" != "$expected" ]; then
    printf '%s\n' "unexpected dependency conflicts:" "$actual" >&2
    exit 1
fi
