import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useQueueDockCollapsePersistence,
  readQueueDockCollapsed,
  writeQueueDockCollapsed,
  getQueueDockStorageKey,
} from '../useQueueDockCollapsePersistence';

describe('useQueueDockCollapsePersistence', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('generates consistent storage keys for valid chat IDs', () => {
    expect(getQueueDockStorageKey('chat-123')).toBe('myrm:queue-dock-collapsed:chat-123');
    expect(getQueueDockStorageKey(null)).toBeNull();
    expect(getQueueDockStorageKey('')).toBeNull();
  });

  it('reads and writes collapse state correctly in localStorage', () => {
    expect(readQueueDockCollapsed('chat-1', false)).toBe(false);

    writeQueueDockCollapsed('chat-1', true);
    expect(readQueueDockCollapsed('chat-1', false)).toBe(true);

    writeQueueDockCollapsed('chat-1', false);
    expect(readQueueDockCollapsed('chat-1', true)).toBe(false);
  });

  it('manages collapse state and persists changes across hook calls', () => {
    const { result, rerender } = renderHook(
      ({ chatId }) => useQueueDockCollapsePersistence(chatId, false),
      { initialProps: { chatId: 'chat-abc' } },
    );

    expect(result.current.isCollapsed).toBe(false);

    act(() => {
      result.current.toggleCollapsed();
    });

    expect(result.current.isCollapsed).toBe(true);
    expect(readQueueDockCollapsed('chat-abc')).toBe(true);

    // Switch to another chat that has no saved state
    rerender({ chatId: 'chat-xyz' });
    expect(result.current.isCollapsed).toBe(false);

    // Switch back to original chat
    rerender({ chatId: 'chat-abc' });
    expect(result.current.isCollapsed).toBe(true);
  });
});
