import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

describe('useComputerUseEscapeAbort', () => {
  const stopMessage = vi.fn();
  let listeners: Array<{ type: string; fn: (e: KeyboardEvent) => void; capture: boolean }> = [];

  beforeEach(() => {
    listeners = [];
    stopMessage.mockReset();
    vi.spyOn(window, 'addEventListener').mockImplementation((type, fn, options) => {
      listeners.push({
        type: String(type),
        fn: fn as (e: KeyboardEvent) => void,
        capture: Boolean(options),
      });
    });
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => {});

    useChatStore.setState({
      chatId: 'chat-1',
      loading: true,
      currentBuiltinTools: ['computer_use'],
      stopMessage,
    } as Partial<ReturnType<typeof useChatStore.getState>>);
    useDesktopInspectorStore.setState({ engagedChatId: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls stopMessage on Escape during computer_use turn', async () => {
    const mod = await import('../useComputerUseEscapeAbort');
    renderHook(() => mod.useComputerUseEscapeAbort());

    const entry = listeners.find((l) => l.type === 'keydown' && l.capture);
    expect(entry).toBeDefined();

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    entry!.fn(event);

    expect(stopMessage).toHaveBeenCalledTimes(1);
  });

  it('ignores Escape when not loading', async () => {
    useChatStore.setState({ loading: false });
    const mod = await import('../useComputerUseEscapeAbort');
    renderHook(() => mod.useComputerUseEscapeAbort());

    const entry = listeners.find((l) => l.type === 'keydown' && l.capture);
    entry!.fn(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));

    expect(stopMessage).not.toHaveBeenCalled();
  });
});
