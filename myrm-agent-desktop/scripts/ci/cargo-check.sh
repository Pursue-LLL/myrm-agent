#!/usr/bin/env bash
# Desktop Rust compile gate: stub sidecars → cargo check → platform-neutral unit tests.
set -euo pipefail

DESKTOP_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_ROOT/.." && pwd)"
TAURI_DIR="$DESKTOP_ROOT/src-tauri"
FRONTEND_STANDALONE="$REPO_ROOT/myrm-agent-frontend/.next/standalone/myrm-agent-frontend"

bash "$REPO_ROOT/scripts/ci/desktop-release/prepare-check-stub-sidecars.sh"

mkdir -p "$FRONTEND_STANDALONE"
if [[ ! -f "$FRONTEND_STANDALONE/server.js" ]]; then
  printf '%s\n' '// CI stub for cargo check' >"$FRONTEND_STANDALONE/server.js"
  echo "[desktop-cargo-check] stub frontend standalone at $FRONTEND_STANDALONE"
fi

cd "$TAURI_DIR"
cargo check --locked
# Multiple libtest filters are OR-ed:
#   config::tests                      settings persistence
#   commands::privacy_curtain          curtain state file bridge and the watcher decision table
#                                      (incl. the unlock-lease level rule)
#   commands::visual_approval_overlay  overlay geometry, window labels and page rendering
#   commands::pet_surface              pet overlay page address on the product origin
#   commands::session_window           session window page address on the product origin
#   utils::protocol_page               custom-protocol page primitives
#   runtime::product_origin            product page origin and URL building
#   app::chain                         shipped tauri.conf.json is accepted by every plugin (in-process
#                                      boot with the real context) and the shell-open link scope
#   ipc_security::acl_tests            window x origin x command ACL contract (in-process, real
#                                      ACL manifests) and its agreement with the app-level gate
#   ipc_security::tests::build_manifest_commands_are_covered_by_policy / command_registry
#                                      every registered command has a sender policy, no duplicates
#   app::setup                         which windows the app-level window policy governs
cargo test --locked -- config::tests commands::privacy_curtain commands::visual_approval_overlay \
  commands::pet_surface commands::session_window utils::protocol_page runtime::product_origin \
  app::chain ipc_security::acl_tests \
  ipc_security::tests::build_manifest_commands_are_covered_by_policy \
  ipc_security::tests::command_registry app::setup --nocapture

echo "[desktop-cargo-check] OK"
