/** @vitest-environment jsdom */

const markChatAsRead = vi.fn();
const isUserPresent = vi.fn();

vi.mock('@/services/chat', () => ({
  markChatAsRead: (...args: unknown[]) => markChatAsRead(...args),
}));
vi.mock('@/lib/utils/userPresence', () => ({ isUserPresent: () => isUserPresent() }));

import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { usePresenceReadMark } from '../usePresenceReadMark';

const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event('visibilitychange'));
};

const digestEvent = (chatId: string, phase: string) =>
  window.dispatchEvent(new CustomEvent('run-digest-updated', { detail: { chat_id: chatId, digest: { phase } } }));

describe('usePresenceReadMark', () => {
  beforeEach(() => {
    markChatAsRead.mockReset().mockResolvedValue(undefined);
    isUserPresent.mockReset().mockReturnValue(true);
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
  });

  it('stamps when a chat with content opens while the user is present', () => {
    renderHook(() => usePresenceReadMark('chat-1', true));

    expect(markChatAsRead).toHaveBeenCalledWith('chat-1', { silent: true });
  });

  it('does not stamp when the user is away', () => {
    isUserPresent.mockReturnValue(false);

    renderHook(() => usePresenceReadMark('chat-1', true));

    expect(markChatAsRead).not.toHaveBeenCalled();
  });

  it('does not stamp a chat the server has not stored yet', () => {
    renderHook(() => usePresenceReadMark('chat-1', false));
    renderHook(() => usePresenceReadMark('', true));

    expect(markChatAsRead).not.toHaveBeenCalled();
  });

  it('stamps when the window returns to the foreground', () => {
    isUserPresent.mockReturnValue(false);
    renderHook(() => usePresenceReadMark('chat-1', true));

    isUserPresent.mockReturnValue(true);
    window.dispatchEvent(new Event('focus'));

    expect(markChatAsRead).toHaveBeenCalledTimes(1);
  });

  it('stamps when the page becomes visible again while the user is present', () => {
    isUserPresent.mockReturnValue(false);
    renderHook(() => usePresenceReadMark('chat-1', true));

    isUserPresent.mockReturnValue(true);
    setHidden(false);

    expect(markChatAsRead).toHaveBeenCalledTimes(1);
  });

  it.each(['completed', 'error', 'cancelled'])('stamps when its turn ends as %s while present', (phase) => {
    renderHook(() => usePresenceReadMark('chat-1', true));
    markChatAsRead.mockClear();

    digestEvent('chat-1', phase);

    expect(markChatAsRead).toHaveBeenCalledTimes(1);
  });

  it('ignores progress of the turn and turns of other chats', () => {
    renderHook(() => usePresenceReadMark('chat-1', true));
    markChatAsRead.mockClear();

    digestEvent('chat-1', 'running');
    digestEvent('chat-1', 'waiting_approval');
    digestEvent('chat-2', 'completed');

    expect(markChatAsRead).not.toHaveBeenCalled();
  });

  it('does not stamp a turn that ended while the user was away', () => {
    renderHook(() => usePresenceReadMark('chat-1', true));
    markChatAsRead.mockClear();
    isUserPresent.mockReturnValue(false);

    digestEvent('chat-1', 'completed');

    expect(markChatAsRead).not.toHaveBeenCalled();
  });

  describe('when the user stops looking', () => {
    const loseFocus = () => {
      isUserPresent.mockReturnValue(false);
      window.dispatchEvent(new Event('blur'));
    };

    it('stamps on blur even though the page is no longer present by then', () => {
      renderHook(() => usePresenceReadMark('chat-1', true));
      markChatAsRead.mockClear();

      loseFocus();

      expect(markChatAsRead).toHaveBeenCalledTimes(1);
      expect(markChatAsRead).toHaveBeenCalledWith('chat-1', { silent: true });
    });

    it('stamps when the page is hidden', () => {
      renderHook(() => usePresenceReadMark('chat-1', true));
      markChatAsRead.mockClear();

      isUserPresent.mockReturnValue(false);
      setHidden(true);

      expect(markChatAsRead).toHaveBeenCalledTimes(1);
    });

    it('stamps once when blur and hide arrive together, and not for a hide after the user was already away', () => {
      renderHook(() => usePresenceReadMark('chat-1', true));
      markChatAsRead.mockClear();

      loseFocus();
      setHidden(true);

      expect(markChatAsRead).toHaveBeenCalledTimes(1);
    });

    it('does not stamp when the user was away from the start', () => {
      isUserPresent.mockReturnValue(false);
      renderHook(() => usePresenceReadMark('chat-1', true));

      window.dispatchEvent(new Event('blur'));
      setHidden(true);

      expect(markChatAsRead).not.toHaveBeenCalled();
    });

    it('stamps again after the user comes back and leaves a second time', () => {
      renderHook(() => usePresenceReadMark('chat-1', true));
      loseFocus();
      isUserPresent.mockReturnValue(true);
      window.dispatchEvent(new Event('focus'));
      markChatAsRead.mockClear();

      loseFocus();

      expect(markChatAsRead).toHaveBeenCalledTimes(1);
    });

    it('stamps the chat being left when the user switches chats while looking', () => {
      const { rerender } = renderHook(({ id }) => usePresenceReadMark(id, true), { initialProps: { id: 'chat-1' } });
      markChatAsRead.mockClear();

      rerender({ id: 'chat-2' });

      expect(markChatAsRead.mock.calls.map(([id]) => id)).toEqual(['chat-1', 'chat-2']);
    });

    it('does not stamp the chat being left when the page is already away', () => {
      const { rerender } = renderHook(({ id }) => usePresenceReadMark(id, true), { initialProps: { id: 'chat-1' } });
      loseFocus();
      markChatAsRead.mockClear();

      rerender({ id: 'chat-2' });

      expect(markChatAsRead).not.toHaveBeenCalled();
    });
  });

  it('survives a failed stamp and stops listening on unmount', async () => {
    markChatAsRead.mockRejectedValue(new Error('offline'));
    const { unmount } = renderHook(() => usePresenceReadMark('chat-1', true));
    await Promise.resolve();
    unmount();
    markChatAsRead.mockClear();

    digestEvent('chat-1', 'completed');
    window.dispatchEvent(new Event('focus'));

    expect(markChatAsRead).not.toHaveBeenCalled();
  });
});
