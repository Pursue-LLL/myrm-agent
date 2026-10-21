import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkspaceScopeStore } from '../useWorkspaceScopeStore';

describe('useWorkspaceScopeStore', () => {
  beforeEach(() => {
    useWorkspaceScopeStore.getState().resetState();
  });

  it('initializes with personal scope and closed dropdown', () => {
    const store = useWorkspaceScopeStore.getState();
    expect(store.currentScope).toBe('personal');
    expect(store.isScopeDropdownOpen).toBe(false);
    expect(store.teams.length).toBeGreaterThan(0);
    expect(store.lastIsolationAudit).toBeNull();
  });

  it('switches to team scope and guarantees Zero-Leak isolation', () => {
    const store = useWorkspaceScopeStore.getState();
    const audit = store.switchScope('team', 'team-open-labs');

    expect(audit.fromScope).toBe('personal');
    expect(audit.toScope).toBe('team');
    expect(audit.activeSessionPurged).toBe(true);
    expect(audit.localSecretKeysHidden).toBe(true);
    expect(audit.isZeroLeakGuaranteed).toBe(true);

    const updated = useWorkspaceScopeStore.getState();
    expect(updated.currentScope).toBe('team');
    expect(updated.activeTeamId).toBe('team-open-labs');
    expect(updated.lastIsolationAudit).toEqual(audit);
  });

  it('switches back to personal scope and unhides local keys', () => {
    const store = useWorkspaceScopeStore.getState();
    store.switchScope('team');
    expect(useWorkspaceScopeStore.getState().currentScope).toBe('team');

    const audit = store.switchScope('personal');
    expect(audit.fromScope).toBe('team');
    expect(audit.toScope).toBe('personal');
    expect(audit.activeSessionPurged).toBe(true);
    expect(audit.localSecretKeysHidden).toBe(false);

    expect(useWorkspaceScopeStore.getState().currentScope).toBe('personal');
  });

  it('toggles dropdown visibility', () => {
    const store = useWorkspaceScopeStore.getState();
    expect(store.isScopeDropdownOpen).toBe(false);

    store.toggleDropdown();
    expect(useWorkspaceScopeStore.getState().isScopeDropdownOpen).toBe(true);

    store.toggleDropdown(false);
    expect(useWorkspaceScopeStore.getState().isScopeDropdownOpen).toBe(false);
  });

  it('selects and clears discovery chips', () => {
    const store = useWorkspaceScopeStore.getState();
    const prompt = store.selectDiscoveryChip('chip-make-dashboard');

    expect(prompt).toContain('Interactive Dashboard');
    expect(useWorkspaceScopeStore.getState().selectedChipResult).toBe(prompt);

    store.clearSelectedChip();
    expect(useWorkspaceScopeStore.getState().selectedChipResult).toBeNull();
  });
});
