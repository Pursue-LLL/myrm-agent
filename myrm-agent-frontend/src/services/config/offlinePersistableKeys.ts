/**
 * [INPUT]
 * - `./types` ConfigKey (POS: closed union of every config key the sync layer knows)
 *
 * [OUTPUT]
 * OFFLINE_PERSISTABLE_CONFIG_KEYS: the config keys whose pending changes may be written to browser storage in clear text.
 *
 * [POS]
 * Allowlist the offline queue consults before it writes to `localStorage`. Only keys the server also stores unsealed
 * belong here; every other key (provider keys, credentials, the local-model key …) is retried from memory and dropped
 * on reload instead of landing on disk next to the page's scripts.
 *
 * An allowlist rather than a denylist on purpose: a key added later stays out of browser storage until it is listed.
 * The server-side parity test `tests/architecture/test_offline_persistable_keys_parity.py` requires this set to equal
 * the frontend config keys minus the server's `SENSITIVE_CONFIG_KEYS`, so a sealed key can never be listed.
 */
import type { ConfigKey } from './types';

export const OFFLINE_PERSISTABLE_CONFIG_KEYS: ReadonlySet<ConfigKey> = new Set<ConfigKey>([
  'budget_policy',
  'channels',
  'chatSettings',
  'commands',
  'personalSettings',
  'securityConfig',
  'securityDashboardSettings',
]);
