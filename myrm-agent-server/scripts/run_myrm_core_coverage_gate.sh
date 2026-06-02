#!/usr/bin/env bash
# Gate: critical search+context path in myrm_agent_harness must stay >= 80% covered.
# Run from repo: myrm-agent-server/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
