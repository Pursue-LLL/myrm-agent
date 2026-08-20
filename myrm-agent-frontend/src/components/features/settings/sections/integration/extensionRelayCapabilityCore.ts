export const REQUIRED_RELAY_CAPABILITIES = ['navigate_url', 'list_tabs', 'attach_debugger', 'detach_debugger'] as const;

export type RelayCapabilityKey = (typeof REQUIRED_RELAY_CAPABILITIES)[number];

export type RelayCapabilityStatusKind = 'not_connected' | 'syncing' | 'ready' | 'upgrade_required';

export interface RelayCapabilityRow {
  key: RelayCapabilityKey;
  available: boolean;
}

export function buildRelayCapabilityRows(capabilities: readonly string[]): RelayCapabilityRow[] {
  const capabilitySet = new Set(capabilities);
  return REQUIRED_RELAY_CAPABILITIES.map((key) => ({
    key,
    available: capabilitySet.has(key),
  }));
}

export function listMissingRelayCapabilities(capabilities: readonly string[]): RelayCapabilityKey[] {
  const capabilitySet = new Set(capabilities);
  return REQUIRED_RELAY_CAPABILITIES.filter((key) => !capabilitySet.has(key));
}

export function resolveRelayCapabilityStatusKind(
  connected: boolean,
  handshakeReady: boolean,
  capabilities: readonly string[],
): RelayCapabilityStatusKind {
  if (!connected) {
    return 'not_connected';
  }
  if (!handshakeReady) {
    return 'syncing';
  }
  if (listMissingRelayCapabilities(capabilities).length === 0) {
    return 'ready';
  }
  return 'upgrade_required';
}
