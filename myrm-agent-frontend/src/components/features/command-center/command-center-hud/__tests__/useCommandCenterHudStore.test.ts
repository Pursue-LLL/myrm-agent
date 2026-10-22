import { describe, it, expect, beforeEach } from 'vitest';
import { useCommandCenterHudStore } from '../useCommandCenterHudStore';

describe('useCommandCenterHudStore', () => {
  beforeEach(() => {
    useCommandCenterHudStore.getState().reset();
  });

  it('initializes with default states', () => {
    const state = useCommandCenterHudStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.selectedTimeRange).toBe('7d');
    expect(state.gatewayHealth).toBe('healthy');
    expect(state.diagnosticChecks.length).toBe(4);
    expect(state.pinnedWorkstreams.length).toBe(4);
    expect(state.spendSummaries['7d'].totalTokens).toBeGreaterThan(0);
  });

  it('manages modal visibility with openHud, closeHud, and toggleHud', () => {
    const { openHud, closeHud, toggleHud, setSearchQuery } =
      useCommandCenterHudStore.getState();

    openHud();
    expect(useCommandCenterHudStore.getState().isOpen).toBe(true);

    setSearchQuery('test query');
    expect(useCommandCenterHudStore.getState().searchQuery).toBe('test query');

    closeHud();
    expect(useCommandCenterHudStore.getState().isOpen).toBe(false);
    // closeHud 会清空搜索框
    expect(useCommandCenterHudStore.getState().searchQuery).toBe('');

    toggleHud();
    expect(useCommandCenterHudStore.getState().isOpen).toBe(true);
  });

  it('switches time ranges correctly', () => {
    const { setSelectedTimeRange } = useCommandCenterHudStore.getState();

    setSelectedTimeRange('30d');
    expect(useCommandCenterHudStore.getState().selectedTimeRange).toBe('30d');

    setSelectedTimeRange('90d');
    expect(useCommandCenterHudStore.getState().selectedTimeRange).toBe('90d');
  });

  it('toggles pin status on workstreams', () => {
    const { togglePinWorkstream } = useCommandCenterHudStore.getState();

    // ws-1 默认 isPinned 为 true
    togglePinWorkstream('ws-1');
    const ws1 = useCommandCenterHudStore
      .getState()
      .pinnedWorkstreams.find((w) => w.id === 'ws-1');
    expect(ws1?.isPinned).toBe(false);

    togglePinWorkstream('ws-1');
    expect(
      useCommandCenterHudStore
        .getState()
        .pinnedWorkstreams.find((w) => w.id === 'ws-1')?.isPinned
    ).toBe(true);
  });

  it('runs system doctor diagnostic and updates checks', () => {
    const { runDoctor } = useCommandCenterHudStore.getState();
    runDoctor();

    const state = useCommandCenterHudStore.getState();
    expect(state.isRunningDoctor).toBe(false);
    expect(state.gatewayHealth).toBe('healthy');
  });

  it('remediates diagnostic issue and marks it resolved', () => {
    const { remediateIssue } = useCommandCenterHudStore.getState();

    remediateIssue('chk-sandbox');
    const check = useCommandCenterHudStore
      .getState()
      .diagnosticChecks.find((c) => c.id === 'chk-sandbox');

    expect(check?.status).toBe('pass');
    expect(check?.remediable).toBe(false);
  });

  it('generates configuration backup snapshot', () => {
    const { backupConfig } = useCommandCenterHudStore.getState();

    const payload = backupConfig();
    expect(payload).toContain('0.21.0-commercial');
    expect(useCommandCenterHudStore.getState().lastBackupPayload).toBe(payload);
  });
});
