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

const digestEvent = (chatId: string, phase: string) =>
  window.dispatchEvent(new CustomEvent('run-digest-updated', { detail: { chat_id: chatId, digest: { phase } } }));

describe('usePresenceReadMark', () => {
  beforeEach(() => {
    markChatAsRead.mockReset().mockResolvedValue(undefined);
    isUserPresent.mockReset().mockReturnValue(true);
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
