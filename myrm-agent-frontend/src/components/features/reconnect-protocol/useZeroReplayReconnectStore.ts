/**
 * [INPUT]
 * - reconnectProtocolTypes: ReconnectStatus, SessionAtomicSnapshot, LiveDeltaEvent
 *
 * [OUTPUT]
 * - useZeroReplayReconnectStore: Zustand store governing zero-replay reconnect state machine
 *
 * [POS]
 * Client-side state store for Item 36 P0. Strictly under 250 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  LiveDeltaEvent,
  ReconnectStatus,
  SessionAtomicSnapshot,
} from './reconnectProtocolTypes';

interface ZeroReplayReconnectState {
  status: ReconnectStatus;
  activeSessionId: string | null;
  snapshot: SessionAtomicSnapshot | null;
  currentVersion: number;
  currentEpoch: string | null;
  reconnectCount: number;
  lastSyncedAtMs: number | null;
  error: string | null;

  // Actions
  setActiveSession: (sessionId: string | null) => void;
  fetchSnapshot: (sessionId: string) => Promise<SessionAtomicSnapshot | null>;
  setSubscribingLive: () => void;
  setConnected: (epochId: string, version: number) => void;
  handleLiveDelta: (delta: LiveDeltaEvent) => void;
  setReconnecting: () => void;
  setDisconnected: (reason?: string) => void;
  forceResync: (sessionId: string) => Promise<void>;
  reset: () => void;
}

export const useZeroReplayReconnectStore = create<ZeroReplayReconnectState>((set, get) => ({
  status: 'idle',
  activeSessionId: null,
  snapshot: null,
  currentVersion: 1,
  currentEpoch: null,
  reconnectCount: 0,
  lastSyncedAtMs: null,
  error: null,

  setActiveSession: (sessionId: string | null) => {
    if (sessionId !== get().activeSessionId) {
      set({
        activeSessionId: sessionId,
        status: sessionId ? 'fetching_snapshot' : 'idle',
        snapshot: null,
        currentVersion: 1,
        currentEpoch: null,
        reconnectCount: 0,
        lastSyncedAtMs: null,
        error: null,
      });
    }
  },

  fetchSnapshot: async (sessionId: string): Promise<SessionAtomicSnapshot | null> => {
    set({ status: 'fetching_snapshot', error: null });
    try {
      const res = await fetch(`/api/v1/chats/${encodeURIComponent(sessionId)}/atomic-snapshot`);
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Failed to fetch atomic snapshot: HTTP ${res.status}`);
      }
      const jsonResponse = (await res.json()) as { data: SessionAtomicSnapshot };
      const snap = jsonResponse.data;

      set({
        snapshot: snap,
        currentVersion: snap.state_version,
        currentEpoch: snap.epoch_id,
        lastSyncedAtMs: snap.snapshot_timestamp_ms,
        error: null,
      });
      return snap;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown snapshot fetch failure';
      set({ status: 'disconnected', error: msg });
      return null;
    }
  },

  setSubscribingLive: () => {
    set({ status: 'subscribing_live' });
  },

  setConnected: (epochId: string, version: number) => {
    set({
      status: 'connected',
      currentEpoch: epochId,
      currentVersion: version,
      error: null,
    });
  },

  handleLiveDelta: (delta: LiveDeltaEvent) => {
    const currentSnap = get().snapshot;
    const newVersion = delta.state_version ?? (get().currentVersion + 1);

    if (currentSnap) {
      const updatedSnap: SessionAtomicSnapshot = {
        ...currentSnap,
        state_version: newVersion,
        status: delta.status ?? currentSnap.status,
        message_count: delta.message_count ?? currentSnap.message_count,
        snapshot_timestamp_ms: delta.server_time_ms ?? Date.now(),
      };
      set({
        snapshot: updatedSnap,
        currentVersion: newVersion,
        lastSyncedAtMs: updatedSnap.snapshot_timestamp_ms,
      });
    } else {
      set({
        currentVersion: newVersion,
        lastSyncedAtMs: delta.server_time_ms ?? Date.now(),
      });
    }
  },

  setReconnecting: () => {
    set((state) => ({
      status: 'reconnecting',
      reconnectCount: state.reconnectCount + 1,
    }));
  },

  setDisconnected: (reason?: string) => {
    set({
      status: 'disconnected',
      error: reason ?? 'Connection disconnected',
    });
  },

  forceResync: async (sessionId: string) => {
    const snap = await get().fetchSnapshot(sessionId);
    if (snap) {
      set({ status: 'subscribing_live' });
    }
  },

  reset: () => {
    set({
      status: 'idle',
      activeSessionId: null,
      snapshot: null,
      currentVersion: 1,
      currentEpoch: null,
      reconnectCount: 0,
      lastSyncedAtMs: null,
      error: null,
    });
  },
}));
