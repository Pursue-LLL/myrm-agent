import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useZeroReplayReconnectStore } from '../useZeroReplayReconnectStore';
import type { SessionAtomicSnapshot } from '../reconnectProtocolTypes';

describe('useZeroReplayReconnectStore', () => {
  beforeEach(() => {
    useZeroReplayReconnectStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default idle state and version 1', () => {
    const state = useZeroReplayReconnectStore.getState();
    expect(state.status).toBe('idle');
    expect(state.activeSessionId).toBeNull();
    expect(state.snapshot).toBeNull();
    expect(state.currentVersion).toBe(1);
    expect(state.currentEpoch).toBeNull();
    expect(state.reconnectCount).toBe(0);
    expect(state.error).toBeNull();
  });

  it('sets active session and resets state machine appropriately', () => {
    useZeroReplayReconnectStore.getState().setActiveSession('session_abc');
    const state = useZeroReplayReconnectStore.getState();
    expect(state.activeSessionId).toBe('session_abc');
    expect(state.status).toBe('fetching_snapshot');
  });

  it('fetches atomic snapshot successfully and updates store', async () => {
    const mockSnapshot: SessionAtomicSnapshot = {
      session_id: 'session_abc',
      epoch_id: 'epoch_123',
      state_version: 7,
      snapshot_timestamp_ms: 1700000000000,
      status: 'running',
      leaf_entry_id: 'leaf_42',
      active_tool_calls: [{ id: 'call_1', tool_name: 'bash' }],
      message_count: 12,
      latest_turn_summary: 'Executing script',
      artifacts_summary: [],
      metadata: {},
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: mockSnapshot }),
    });

    const result = await useZeroReplayReconnectStore.getState().fetchSnapshot('session_abc');
    expect(result).toEqual(mockSnapshot);

    const state = useZeroReplayReconnectStore.getState();
    expect(state.snapshot).toEqual(mockSnapshot);
    expect(state.currentVersion).toBe(7);
    expect(state.currentEpoch).toBe('epoch_123');
    expect(state.lastSyncedAtMs).toBe(1700000000000);
    expect(state.error).toBeNull();
  });

  it('handles snapshot fetch failure gracefully', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => 'Internal Server Error',
    });

    const result = await useZeroReplayReconnectStore.getState().fetchSnapshot('session_abc');
    expect(result).toBeNull();

    const state = useZeroReplayReconnectStore.getState();
    expect(state.status).toBe('disconnected');
    expect(state.error).toContain('Internal Server Error');
  });

  it('updates state version and timestamp upon live delta reception', () => {
    useZeroReplayReconnectStore.getState().setConnected('epoch_test', 3);
    expect(useZeroReplayReconnectStore.getState().status).toBe('connected');
    expect(useZeroReplayReconnectStore.getState().currentVersion).toBe(3);

    useZeroReplayReconnectStore.getState().handleLiveDelta({
      type: 'state_version_advanced',
      state_version: 4,
      status: 'idle',
      message_count: 15,
      server_time_ms: 1700000050000,
    });

    const state = useZeroReplayReconnectStore.getState();
    expect(state.currentVersion).toBe(4);
    expect(state.lastSyncedAtMs).toBe(1700000050000);
  });

  it('increments reconnect count when transitioning to reconnecting', () => {
    useZeroReplayReconnectStore.getState().setReconnecting();
    expect(useZeroReplayReconnectStore.getState().status).toBe('reconnecting');
    expect(useZeroReplayReconnectStore.getState().reconnectCount).toBe(1);

    useZeroReplayReconnectStore.getState().setReconnecting();
    expect(useZeroReplayReconnectStore.getState().reconnectCount).toBe(2);
  });
});
