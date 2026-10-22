/**
 * [INPUT]
 * - Server re-entry identifiers: `config:<key>` / `table:<name>` / `path:<file>`
 *
 * [OUTPUT]
 * - ReentryGroup, reentryGroups: user-facing groups of credentials that must be entered again
 *
 * [POS]
 * Maps backend storage identifiers to a handful of localized categories so technical key
 * names never reach the UI.
 */

export type ReentryGroup = 'modelKeys' | 'mcpConnections' | 'savedSecrets' | 'connectedAccounts';

const GROUP_ORDER: readonly ReentryGroup[] = ['modelKeys', 'mcpConnections', 'savedSecrets', 'connectedAccounts'];

const CONFIG_GROUPS: Readonly<Record<string, ReentryGroup>> = {
  providers: 'modelKeys',
  retrieval: 'modelKeys',
  searchServices: 'modelKeys',
  mcpServers: 'mcpConnections',
  mcpOAuthTokens: 'mcpConnections',
};

const TABLE_GROUPS: Readonly<Record<string, ReentryGroup>> = {
  vault_credentials: 'savedSecrets',
  agent_secrets: 'savedSecrets',
};

const PATH_GROUPS: Readonly<Record<string, ReentryGroup>> = {
  session_vault: 'savedSecrets',
  whatsapp_auth: 'connectedAccounts',
  matrix: 'connectedAccounts',
};

const GROUPS_BY_KIND: Readonly<Record<string, Readonly<Record<string, ReentryGroup>>>> = {
  config: CONFIG_GROUPS,
  table: TABLE_GROUPS,
  path: PATH_GROUPS,
};

function groupOf(identifier: string): ReentryGroup {
  const [kind, name = ''] = identifier.split(':', 2);
  const known = GROUPS_BY_KIND[kind]?.[name];
  // An unrecognised credential file is a saved secret; any other unknown row is an account.
  return known ?? (kind === 'path' ? 'savedSecrets' : 'connectedAccounts');
}

/** Distinct groups in a stable display order. */
export function reentryGroups(identifiers: readonly string[]): ReentryGroup[] {
  const present = new Set(identifiers.map(groupOf));
  return GROUP_ORDER.filter((group) => present.has(group));
}
