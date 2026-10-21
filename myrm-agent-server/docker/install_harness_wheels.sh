#!/bin/sh
# Install pre-built harness dual wheels into the active venv.
# Requires TARGETPLATFORM (BuildKit) and uv on PATH.
set -eu

CORE_ROOT="${1:?core wheels root directory}"
RELEASE_ROOT="${2:?release wheels root directory}"

case "${TARGETPLATFORM:-linux/amd64}" in
  linux/amd64)
    PLAT=linux-x64
    ;;
  linux/arm64)
    PLAT=linux-arm64
    ;;
  *)
    echo "Unsupported TARGETPLATFORM for harness core wheel: ${TARGETPLATFORM}" >&2
    exit 1
    ;;
esac

CORE_DIR="${CORE_ROOT}/${PLAT}"
if [ ! -d "${CORE_DIR}" ]; then
  echo "Core wheel directory not found: ${CORE_DIR}" >&2
  exit 1
fi

set -- "${CORE_DIR}"/*.whl
if [ ! -e "$1" ]; then
  echo "No core wheel found under ${CORE_DIR}" >&2
  exit 1
fi
if [ -n "${2:-}" ]; then
  echo "Expected exactly one core wheel under ${CORE_DIR}, found: $*" >&2
  exit 1
fi
CORE="$1"

REL=$(ls "${RELEASE_ROOT}"/myrm_agent_harness-*.whl 2>/dev/null | grep -v -- '-release\.whl$' | sort | tail -n 1)
if [ -z "${REL}" ] || [ ! -f "${REL}" ]; then
  echo "No stripped release wheel found under ${RELEASE_ROOT}" >&2
  exit 1
fi

echo "Installing harness wheels: core=${CORE} release=${REL}"
uv pip install "${CORE}" "${REL}"
.venv/bin/verify-harness-distribution
