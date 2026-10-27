import type { ConfigKey } from './types';

/**
 * Config keys whose pending changes may be written to browser storage in clear text.
 *
 * The offline queue lives in `localStorage`, so only keys the server also stores unsealed belong here.
 * Everything else (provider keys, credentials, the local-model key …) is retried from memory and is
 * dropped on reload instead of landing on disk next to the page's scripts.
 *
 * An allowlist rather than a denylist on purpose: a key added later stays out of browser storage until
 * someone decides it is safe. The server-side parity test
 * `tests/architecture/test_offline_persistable_keys_parity.py` keeps this set disjoint from the server's
 * `SENSITIVE_CONFIG_KEYS`.
 */
export const OFFLINE_PERSISTABLE_CONFIG_KEYS: ReadonlySet<ConfigKey> = new Set<ConfigKey>([
  'budget_policy',
  'channels',
  'chatSettings',
  'commands',
  'personalSettings',
  'securityConfig',
  'securityDashboardSettings',
]);
