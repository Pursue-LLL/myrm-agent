#!/usr/bin/env bash
# Shared by finalize-release.sh and verify-release.sh (source this file; do not execute).

# Logs an error. Under GitHub Actions it is also an annotation: annotations show on the run summary and through the
# check-runs API, while the step log needs a signed-in session, so a failure stays diagnosable from the outside.
report() {
  local message="$1"
  echo "$message" >&2
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    message="${message//'%'/%25}"
    message="${message//$'\r'/%0D}"
    message="${message//$'\n'/%0A}"
    echo "::error title=desktop release::${message}"
  fi
}

fail() {
  report "$1"
  exit 1
}

# Rewrites TAG to the release tag it names: `0.1.40` and ` v0.1.40 ` both mean `v0.1.40`.
use_release_tag() {
  local tag="${TAG//[[:space:]]/}"
  tag="v${tag#v}"
  [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)*$ ]] \
    || fail "Release tag must look like v1.2.3, got '${TAG}'"
  TAG="$tag"
}
