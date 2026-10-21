#!/usr/bin/env bash
# Gate: critical search+context path in myrm_agent_harness must stay >= 80% covered.
# Skipped when ../myrm-agent-harness is not checked out beside this server repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HARNESS_TESTS="${ROOT}/../myrm-agent-harness/tests"
if [[ ! -d "${HARNESS_TESTS}" ]]; then
  echo "SKIP: ../myrm-agent-harness not found." >&2
  exit 0
fi
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
exec uv run pytest ../myrm-agent-harness/tests \
  --ignore=../myrm-agent-harness/tests/toolkits/browser \
  --ignore=../myrm-agent-harness/tests/integration \
  --ignore=../myrm-agent-harness/tests/performance \
  -m "not docker" \
  --cov=myrm_agent_harness.utils.context_format \
  --cov=myrm_agent_harness.toolkits.web_search \
  --cov-fail-under=80 \
  --benchmark-disable \
  -q "$@"
