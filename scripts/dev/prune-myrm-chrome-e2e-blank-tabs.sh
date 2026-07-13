#!/usr/bin/env bash
# Prune orphan and duplicate Myrm E2E Chrome tabs (:9333).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

MONOREPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
MUX_BIN="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs"

PRUNE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) PRUNE=0 ;;
    -h|--help)
      echo "Usage: prune-myrm-chrome-e2e-blank-tabs.sh [--dry-run]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if ! myrm_chrome_e2e_cdp_healthy; then
  echo "MYRM_CHROME_PRUNE_SKIP: CDP not ready on port ${MYRM_CHROME_E2E_PORT}"
  exit 0
fi

export MYRM_CHROME_E2E_PORT
export MYRM_PRUNE="${PRUNE}"
export CDMCP_MUX_STATUS_BIN="${MUX_BIN}"
export CDMCP_MUX_NODE="${CDMCP_MUX_NODE:-$(command -v node)}"

PREFLIGHT_PY="${SCRIPT_DIR}/../../myrm-agent-server/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

"${PREFLIGHT_PY}" - <<'PY'
import json
import os
import subprocess
import sys
import urllib.request

port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
prune = os.environ.get("MYRM_PRUNE", "1") == "1"
ui_origin = "http://127.0.0.1:3000"
list_url = f"http://127.0.0.1:{port}/json/list"


def mux_context_count() -> int | None:
    mux_bin = os.environ.get("CDMCP_MUX_STATUS_BIN", "")
    node_bin = os.environ.get("CDMCP_MUX_NODE", "node")
    if not mux_bin or not os.path.isfile(mux_bin):
        return None
    try:
        proc = subprocess.run(
            [node_bin, mux_bin, "status"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        contexts = data.get("contexts")
        if not isinstance(contexts, list):
            return None
        return sum(1 for ctx in contexts if isinstance(ctx, dict))
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


try:
    with urllib.request.urlopen(list_url, timeout=5) as resp:
        pages = json.load(resp)
except OSError as exc:
    print(f"MYRM_CHROME_PRUNE_SKIP: {exc}", file=sys.stderr)
    sys.exit(0)

if not isinstance(pages, list):
    print("MYRM_CHROME_PRUNE_SKIP: invalid /json/list payload", file=sys.stderr)
    sys.exit(0)

active_mux_contexts = mux_context_count()
if active_mux_contexts is None:
    print("MYRM_CHROME_PRUNE_SKIP: mux ownership unavailable")
    sys.exit(0)
if active_mux_contexts:
    print(f"MYRM_CHROME_PRUNE_SKIP: active_mux_contexts={active_mux_contexts}")
    sys.exit(0)

orphan_prefixes = ("about:blank", "chrome-error://", "chrome://newtab/")
orphan_exact = ("",)
orphan_suffixes = ("/sw.js",)

to_close: list[str] = []
seen_close: set[str] = set()

def mark_close(page_id: str) -> None:
    if page_id not in seen_close:
        seen_close.add(page_id)
        to_close.append(page_id)


for page in pages:
    if not isinstance(page, dict):
        continue
    url = page.get("url") or ""
    page_id = page.get("id")
    if not isinstance(page_id, str) or not page_id:
        continue
    if url in orphan_exact:
        mark_close(page_id)
        continue
    if any(url.startswith(p) for p in orphan_prefixes):
        mark_close(page_id)
        continue
    if any(url.endswith(s) for s in orphan_suffixes):
        mark_close(page_id)
        continue
    if url.startswith("chrome://"):
        mark_close(page_id)

by_url: dict[str, list[str]] = {}
for page in pages:
    if not isinstance(page, dict):
        continue
    url = page.get("url") or ""
    page_id = page.get("id")
    if not isinstance(page_id, str) or not page_id:
        continue
    if page_id in seen_close:
        continue
    if not url.startswith(ui_origin):
        continue
    by_url.setdefault(url, []).append(page_id)

dup_closed = 0
for url, ids in by_url.items():
    if len(ids) <= 1:
        continue
    for page_id in ids[:-1]:
        mark_close(page_id)
        dup_closed += 1

closed = 0
for page_id in to_close:
    close_url = f"http://127.0.0.1:{port}/json/close/{page_id}"
    if not prune:
        print(f"MYRM_CHROME_PRUNE_DRY: would close {page_id}")
        continue
    try:
        urllib.request.urlopen(close_url, timeout=3).read()
        closed += 1
    except OSError:
        pass

action = "closed" if prune else "would_close"
print(
    f"MYRM_CHROME_PRUNE_OK: {action}={closed} "
    f"total_targets={len(to_close)} dup_candidates={dup_closed}"
)
PY
