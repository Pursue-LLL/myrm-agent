/**
 * Default ports of the shared dev stack for the Node E2E helpers.
 * The shared stack lives on ports disjoint from the user's stack and the desktop sidecar (8080 / 3000).
 *
 * [INPUT]
 * - process.env (POS: MYRM_SHARED_BACKEND_PORT / MYRM_SHARED_FRONTEND_PORT overrides exported by the launchers)
 *
 * [OUTPUT]
 * - SHARED_BACKEND_PORT / SHARED_FRONTEND_PORT, sharedApiBase(), sharedUiBase()
 *
 * [POS]
 * Default ports of the user, shared dev and isolated stacks — SSOT; Node mirror of e2e_core/dev_ports.py and dev_state_paths.sh (a contract test pins parity).
 */

export const SHARED_BACKEND_PORT = 28080;
export const SHARED_FRONTEND_PORT = 23000;

function portFromEnv(name, fallback) {
  const raw = process.env[name]?.trim();
  return raw && /^\d+$/.test(raw) ? Number(raw) : fallback;
}

export function sharedApiBase() {
  return `http://127.0.0.1:${portFromEnv('MYRM_SHARED_BACKEND_PORT', SHARED_BACKEND_PORT)}`;
}

export function sharedUiBase() {
  return `http://127.0.0.1:${portFromEnv('MYRM_SHARED_FRONTEND_PORT', SHARED_FRONTEND_PORT)}`;
}
