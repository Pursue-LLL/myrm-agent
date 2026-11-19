import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSessionStateSync } from '../useSessionStateSync';
import type { VoiceSessionMode } from '../types';

type SyncProps = Parameters<typeof useSessionStateSync>[0];

/** Mounts the hook the way a fresh session sees it: transports disconnected, session not yet started. */
function setup(mode: VoiceSessionMode) {
  const sessionActiveRef = { current: false };
  const setSessionState = vi.fn();
  const initialProps: SyncProps = {
    mode,
    agentBridgeState: 'disconnected',
    realtimeState: 'idle',
    geminiLiveState: 'idle',
    sessionActiveRef,
    setSessionState,
  };
  const hook = renderHook((props: SyncProps) => useSessionStateSync(props), { initialProps });
  return { ...hook, initialProps, sessionActiveRef, setSessionState };
}

describe('useSessionStateSync', () => {
  it.each([
    ['listening', 'listening'],
    ['agent_thinking', 'processing'],
    ['agent_speaking', 'speaking'],
  ] as const)('agent bridge %s maps to session state %s', (agentBridgeState, expected) => {
    const { rerender, initialProps, setSessionState } = setup('agent_bridge');

    rerender({ ...initialProps, agentBridgeState });

    expect(setSessionState).toHaveBeenCalledWith(expected);
  });

  it.each([
    ['connecting', 'listening'],
    ['listening', 'listening'],
    ['thinking', 'processing'],
    ['speaking', 'speaking'],
  ] as const)('realtime %s maps to session state %s', (realtimeState, expected) => {
    const { rerender, initialProps, setSessionState } = setup('openai_realtime');

    rerender({ ...initialProps, realtimeState });

    expect(setSessionState).toHaveBeenCalledWith(expected);
  });

  it.each([
    ['connecting', 'listening'],
    ['listening', 'listening'],
    ['thinking', 'processing'],
    ['speaking', 'speaking'],
  ] as const)('gemini live %s maps to session state %s', (geminiLiveState, expected) => {
    const { rerender, initialProps, setSessionState } = setup('gemini_live');

    rerender({ ...initialProps, geminiLiveState });

    expect(setSessionState).toHaveBeenCalledWith(expected);
  });

  it.each([
    ['agent_bridge', 'agentBridgeState', 'connecting', 'disconnected'],
    ['openai_realtime', 'realtimeState', 'listening', 'error'],
    ['openai_realtime', 'realtimeState', 'listening', 'idle'],
    ['gemini_live', 'geminiLiveState', 'listening', 'error'],
    ['gemini_live', 'geminiLiveState', 'listening', 'idle'],
  ] as const)('%s dropping from %s %s to %s ends a running session', (mode, key, running, dropped) => {
    const { rerender, initialProps, sessionActiveRef, setSessionState } = setup(mode);
    sessionActiveRef.current = true;
    rerender({ ...initialProps, [key]: running });
    setSessionState.mockClear();

    rerender({ ...initialProps, [key]: dropped });

    expect(sessionActiveRef.current).toBe(false);
    expect(setSessionState).toHaveBeenCalledTimes(1);
    expect(setSessionState).toHaveBeenCalledWith('inactive');
  });

  it('a dropped connection leaves an already stopped session alone', () => {
    const { rerender, initialProps, setSessionState } = setup('agent_bridge');
    rerender({ ...initialProps, agentBridgeState: 'connecting' });

    rerender({ ...initialProps, agentBridgeState: 'disconnected' });

    expect(setSessionState).not.toHaveBeenCalled();
  });

  it('follows only the transport that owns the current mode', () => {
    const { rerender, initialProps, setSessionState } = setup('openai_realtime');

    rerender({ ...initialProps, agentBridgeState: 'agent_speaking', geminiLiveState: 'speaking' });

    expect(setSessionState).not.toHaveBeenCalled();
  });

  it('does not mirror any transport in audio-only mode', () => {
    const { rerender, initialProps, setSessionState } = setup('audio_only');

    rerender({
      ...initialProps,
      agentBridgeState: 'agent_speaking',
      realtimeState: 'speaking',
      geminiLiveState: 'speaking',
    });

    expect(setSessionState).not.toHaveBeenCalled();
  });
});
