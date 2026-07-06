#!/usr/bin/env bash
# Cron capability_gap API regression (agent-stream). Requires backend :8080 + .env.test keys.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/myrm-agent-server"
if [[ -f .env.test ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.test
  set +a
fi
cd "$ROOT"
exec bun scripts/dev/cron-gap-e2e-prepare.mjs
