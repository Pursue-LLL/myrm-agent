import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockInitializeChat = vi.fn();
const mockGetState = vi.fn();
vi.mock('@/store/useChatStore', () => ({
  default: { getState: () => mockGetState() },
}));

const mockTogglePanel = vi.fn();
const mockFetchSnapshot = vi.fn();
const mockInspectorGetState = vi.fn();
vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: { getState: () => mockInspectorGetState() },
}));

let mockIsTauri = false;
vi.mock('@/lib/utils/clipboardUtils', () => ({
  isTauri: () => mockIsTauri,
}));

describe('useGlobalShortcuts', () => {
  let handler: ((e: KeyboardEvent) => void) | null = null;
  const listeners: Array<{ type: string; fn: EventListenerOrEventListenerObject; capture: boolean }> = [];

  beforeEach(() => {
    vi.resetAllMocks();
    handler = null;
    listeners.length = 0;

    mockGetState.mockReturnValue({
      initializeChat: mockInitializeChat,
      chatHistoryItems: [
        { id: 'chat-a', isPinned: true, pinOrder: 0 },
        { id: 'chat-b', isPinned: true, pinOrder: 1 },
        { id: 'chat-c', isPinned: false },
      ],
    });

    mockInspectorGetState.mockReturnValue({
      isOpen: false,
      togglePanel: mockTogglePanel,
      fetchSnapshot: mockFetchSnapshot,
    });

    vi.spyOn(window, 'addEventListener').mockImplementation(
      (type: string, fn: EventListenerOrEventListenerObject, options?: boolean | AddEventListenerOptions) => {
        const capture = typeof options === 'boolean' ? options : !!(options as AddEventListenerOptions)?.capture;
        listeners.push({ type, fn, capture });
        if (type === 'keydown') handler = fn as (e: KeyboardEvent) => void;
      },
    );

    vi.spyOn(window, 'removeEventListener').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function fireKey(opts: Partial<KeyboardEvent>) {
    const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...opts });
    vi.spyOn(event, 'preventDefault');
    vi.spyOn(event, 'stopPropagation');
    handler?.(event);
    return event;
  }

  async function mountHook() {
    const mod = await import('../useGlobalShortcuts');
    return renderHook(() => mod.useGlobalShortcuts());
  }

  describe('Tauri desktop environment', () => {
    beforeEach(() => {
      mockIsTauri = true;
    });

    it('registers keydown listener in capture phase', async () => {
      await mountHook();
      const entry = listeners.find((l) => l.type === 'keydown');
      expect(entry).toBeDefined();
      expect(entry?.capture).toBe(true);
    });

    it('creates new chat on Cmd+N', async () => {
      await mountHook();
      const event = fireKey({ key: 'n', metaKey: true, code: 'KeyN' });
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
      expect(mockPush).toHaveBeenCalledWith('/');
      expect(event.preventDefault).toHaveBeenCalled();
    });

    it('creates new chat on Ctrl+N', async () => {
      await mountHook();
      fireKey({ key: 'n', ctrlKey: true, code: 'KeyN' });
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
      expect(mockPush).toHaveBeenCalledWith('/');
    });

    it('ignores Cmd+Shift+N in Tauri (shift guard)', async () => {
      await mountHook();
      fireKey({ key: 'N', metaKey: true, shiftKey: true, code: 'KeyN' });
      expect(mockInitializeChat).not.toHaveBeenCalled();
    });

    it('toggles browser panel on Cmd+B', async () => {
      await mountHook();
      const event = fireKey({ key: 'b', metaKey: true, code: 'KeyB' });
      expect(mockTogglePanel).toHaveBeenCalled();
      expect(event.preventDefault).toHaveBeenCalled();
      expect(event.stopPropagation).toHaveBeenCalled();
    });

    it('fetches snapshot when panel opens on Cmd+B', async () => {
      mockInspectorGetState.mockReturnValue({
        isOpen: false,
        togglePanel: mockTogglePanel,
        fetchSnapshot: mockFetchSnapshot,
      });
      await mountHook();
      fireKey({ key: 'b', metaKey: true, code: 'KeyB' });
      expect(mockFetchSnapshot).toHaveBeenCalled();
    });

    it('does not fetch snapshot when panel closes on Cmd+B', async () => {
      mockInspectorGetState.mockReturnValue({
        isOpen: true,
        togglePanel: mockTogglePanel,
        fetchSnapshot: mockFetchSnapshot,
      });
      await mountHook();
      fireKey({ key: 'B', metaKey: true, code: 'KeyB' });
      expect(mockTogglePanel).toHaveBeenCalled();
      expect(mockFetchSnapshot).not.toHaveBeenCalled();
    });

    it('jumps to pinned chat on Cmd+1', async () => {
      await mountHook();
      const event = fireKey({ key: '1', metaKey: true, code: 'Digit1' });
      expect(mockPush).toHaveBeenCalledWith('/chat-a');
      expect(event.preventDefault).toHaveBeenCalled();
    });

    it('jumps to second pinned chat on Cmd+2', async () => {
      await mountHook();
      fireKey({ key: '2', metaKey: true, code: 'Digit2' });
      expect(mockPush).toHaveBeenCalledWith('/chat-b');
    });

    it('ignores Cmd+digit beyond pinned count', async () => {
      await mountHook();
      fireKey({ key: '9', metaKey: true, code: 'Digit9' });
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('ignores key without modifier', async () => {
      await mountHook();
      fireKey({ key: 'n', code: 'KeyN' });
      expect(mockInitializeChat).not.toHaveBeenCalled();
    });

    it('handles uppercase N with CapsLock', async () => {
      await mountHook();
      fireKey({ key: 'N', metaKey: true, code: 'KeyN' });
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
    });

    it('ignores non-shortcut keys like Cmd+A', async () => {
      await mountHook();
      fireKey({ key: 'a', metaKey: true, code: 'KeyA' });
      expect(mockInitializeChat).not.toHaveBeenCalled();
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('ignores Cmd+0 (Digit0 is not in 1-9 range)', async () => {
      await mountHook();
      fireKey({ key: '0', metaKey: true, code: 'Digit0' });
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('sorts pinned chats by pinOrder regardless of array order', async () => {
      mockGetState.mockReturnValue({
        initializeChat: mockInitializeChat,
        chatHistoryItems: [
          { id: 'z-last', isPinned: true, pinOrder: 5 },
          { id: 'a-first', isPinned: true, pinOrder: 0 },
          { id: 'mid', isPinned: true, pinOrder: 2 },
        ],
      });
      await mountHook();
      fireKey({ key: '1', metaKey: true, code: 'Digit1' });
      expect(mockPush).toHaveBeenCalledWith('/a-first');
      mockPush.mockClear();
      fireKey({ key: '3', metaKey: true, code: 'Digit3' });
      expect(mockPush).toHaveBeenCalledWith('/z-last');
    });

    it('handles pinOrder with undefined values (defaults to 0)', async () => {
      mockGetState.mockReturnValue({
        initializeChat: mockInitializeChat,
        chatHistoryItems: [
          { id: 'no-order', isPinned: true },
          { id: 'has-order', isPinned: true, pinOrder: 1 },
        ],
      });
      await mountHook();
      fireKey({ key: '1', metaKey: true, code: 'Digit1' });
      expect(mockPush).toHaveBeenCalledWith('/no-order');
    });

    it('removes listener on unmount', async () => {
      const removeSpy = vi.spyOn(window, 'removeEventListener');
      const { unmount } = await mountHook();
      unmount();
      expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function), true);
    });

    it('calls stopPropagation on Cmd+N', async () => {
      await mountHook();
      const event = fireKey({ key: 'n', metaKey: true, code: 'KeyN' });
      expect(event.stopPropagation).toHaveBeenCalled();
    });

    it('calls stopPropagation on Cmd+digit for pinned', async () => {
      await mountHook();
      const event = fireKey({ key: '1', metaKey: true, code: 'Digit1' });
      expect(event.stopPropagation).toHaveBeenCalled();
    });

    it('does not call stopPropagation for unmatched digit', async () => {
      await mountHook();
      const event = fireKey({ key: '9', metaKey: true, code: 'Digit9' });
      expect(event.stopPropagation).not.toHaveBeenCalled();
    });
  });

  describe('Web browser environment', () => {
    beforeEach(() => {
      mockIsTauri = false;
    });

    it('requires Shift modifier in web mode', async () => {
      await mountHook();
      fireKey({ key: 'n', metaKey: true, code: 'KeyN' });
      expect(mockInitializeChat).not.toHaveBeenCalled();
    });

    it('creates new chat on Cmd+Shift+N in web', async () => {
      await mountHook();
      fireKey({ key: 'N', metaKey: true, shiftKey: true, code: 'KeyN' });
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
      expect(mockPush).toHaveBeenCalledWith('/');
    });

    it('jumps to pinned chat on Cmd+Shift+1 in web', async () => {
      await mountHook();
      fireKey({ key: '!', metaKey: true, shiftKey: true, code: 'Digit1' });
      expect(mockPush).toHaveBeenCalledWith('/chat-a');
    });

    it('ignores Ctrl+N without Shift in web', async () => {
      await mountHook();
      fireKey({ key: 'n', ctrlKey: true, code: 'KeyN' });
      expect(mockInitializeChat).not.toHaveBeenCalled();
    });

    it('creates new chat on Ctrl+Shift+N in web', async () => {
      await mountHook();
      fireKey({ key: 'N', ctrlKey: true, shiftKey: true, code: 'KeyN' });
      expect(mockInitializeChat).toHaveBeenCalledWith(undefined);
    });

    it('ignores Cmd+Shift+0 in web', async () => {
      await mountHook();
      fireKey({ key: ')', metaKey: true, shiftKey: true, code: 'Digit0' });
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('toggles browser panel on Cmd+Shift+B in web', async () => {
      await mountHook();
      const event = fireKey({ key: 'B', metaKey: true, shiftKey: true, code: 'KeyB' });
      expect(mockTogglePanel).toHaveBeenCalled();
      expect(event.preventDefault).toHaveBeenCalled();
    });

    it('ignores Cmd+B without Shift in web', async () => {
      await mountHook();
      fireKey({ key: 'b', metaKey: true, code: 'KeyB' });
      expect(mockTogglePanel).not.toHaveBeenCalled();
    });
  });
});
