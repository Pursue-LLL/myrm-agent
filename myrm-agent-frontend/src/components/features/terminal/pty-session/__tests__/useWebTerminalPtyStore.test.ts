/**
 * Web Terminal PTY Store Unit Tests
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useWebTerminalPtyStore } from '../useWebTerminalPtyStore';

describe('useWebTerminalPtyStore', () => {
  beforeEach(() => {
    useWebTerminalPtyStore.getState().resetToDefault();
  });

  it('should initialize with default sessions and active session id', () => {
    const state = useWebTerminalPtyStore.getState();
    expect(state.sessions.length).toBeGreaterThanOrEqual(2);
    expect(state.activeSessionId).toBe('pty-session-main');
    expect(state.buffers['pty-session-main']).toBeDefined();
  });

  it('should create new PTY session and set it as active', () => {
    const store = useWebTerminalPtyStore.getState();
    const newId = store.createSession('测试终端', '/workspace/demo');

    const updated = useWebTerminalPtyStore.getState();
    expect(updated.activeSessionId).toBe(newId);
    expect(updated.sessions.some((s) => s.id === newId)).toBe(true);
    expect(updated.buffers[newId]).toBeDefined();
  });

  it('should detach session and keep process running in background', () => {
    const store = useWebTerminalPtyStore.getState();
    store.detachSession('pty-session-main');

    const session = useWebTerminalPtyStore
      .getState()
      .sessions.find((s) => s.id === 'pty-session-main');
    expect(session?.isDetached).toBe(true);
    expect(session?.status).toBe('detached');
  });

  it('should attach session and restore connection', () => {
    const store = useWebTerminalPtyStore.getState();
    store.detachSession('pty-session-main');
    expect(useWebTerminalPtyStore.getState().sessions.find((s) => s.id === 'pty-session-main')?.isDetached).toBe(true);

    store.attachSession('pty-session-main');
    const session = useWebTerminalPtyStore
      .getState()
      .sessions.find((s) => s.id === 'pty-session-main');
    expect(session?.isDetached).toBe(false);
    expect(session?.status).toBe('connected');
  });

  it('should handle keyboard writing into buffer and execution', () => {
    const store = useWebTerminalPtyStore.getState();
    store.writeInput('pty-session-main', 'l');
    store.writeInput('pty-session-main', 's');
    expect(useWebTerminalPtyStore.getState().inputBuffer).toBe('ls');

    // Press Enter to execute
    store.writeInput('pty-session-main', '\r');
    expect(useWebTerminalPtyStore.getState().inputBuffer).toBe('');
  });

  it('should close session and switch active to another', () => {
    const store = useWebTerminalPtyStore.getState();
    store.closeSession('pty-session-main');

    const remaining = useWebTerminalPtyStore.getState().sessions;
    expect(remaining.some((s) => s.id === 'pty-session-main')).toBe(false);
    expect(useWebTerminalPtyStore.getState().activeSessionId).toBe('pty-session-daemon');
  });
});
