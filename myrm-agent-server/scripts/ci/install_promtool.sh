#!/usr/bin/env bash
# Install the pinned promtool release into /usr/local/bin (linux-amd64 CI runners).
# Tests that validate Prometheus rules fail in CI when promtool is missing, so every workflow that
# runs them calls this script instead of carrying its own copy of the pinned version and checksum.
set -euo pipefail

PROMETHEUS_VERSION="3.15.0"
PROMETHEUS_SHA256="2a542df32eac02ee17b9d844fb2aa1de00dafa5476579ba8a3ba862e9d572ea0"

WORK_DIR="${RUNNER_TEMP:-$(mktemp -d)}"
RELEASE_DIR="prometheus-${PROMETHEUS_VERSION}.linux-amd64"
ARCHIVE="${WORK_DIR}/${RELEASE_DIR}.tar.gz"

curl -fsSL -o "${ARCHIVE}" \
  "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/${RELEASE_DIR}.tar.gz"
echo "${PROMETHEUS_SHA256}  ${ARCHIVE}" | sha256sum -c -
tar -xzf "${ARCHIVE}" -C "${WORK_DIR}" "${RELEASE_DIR}/promtool"
sudo install -m 0755 "${WORK_DIR}/${RELEASE_DIR}/promtool" /usr/local/bin/promtool
promtool --version
