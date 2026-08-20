import { describe, expect, it } from 'vitest';

import {
  buildRelayCapabilityRows,
  listMissingRelayCapabilities,
  resolveRelayCapabilityStatusKind,
} from '../extensionRelayCapabilityCore';

describe('extensionRelayCapabilityCore', () => {
  it('marks all relay capabilities unavailable when disconnected contract expects four rows', () => {
    const rows = buildRelayCapabilityRows([]);
    expect(rows).toHaveLength(4);
    expect(rows.every((row) => row.available === false)).toBe(true);
    expect(listMissingRelayCapabilities([])).toEqual([
      'navigate_url',
      'list_tabs',
      'attach_debugger',
      'detach_debugger',
    ]);
  });

  it('detects partial capability sets for upgrade-required UI', () => {
    const rows = buildRelayCapabilityRows(['navigate_url', 'list_tabs']);
    expect(rows.filter((row) => row.available).map((row) => row.key)).toEqual(['navigate_url', 'list_tabs']);
    expect(listMissingRelayCapabilities(['navigate_url', 'list_tabs'])).toEqual(['attach_debugger', 'detach_debugger']);
  });

  it('resolves relay status kind across connection lifecycle', () => {
    expect(resolveRelayCapabilityStatusKind(false, false, [])).toBe('not_connected');
    expect(resolveRelayCapabilityStatusKind(true, false, ['navigate_url'])).toBe('syncing');
    expect(
      resolveRelayCapabilityStatusKind(true, true, ['navigate_url', 'list_tabs', 'attach_debugger', 'detach_debugger']),
    ).toBe('ready');
    expect(resolveRelayCapabilityStatusKind(true, true, ['navigate_url', 'list_tabs'])).toBe('upgrade_required');
  });
});
