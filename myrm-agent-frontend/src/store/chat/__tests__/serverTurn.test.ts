/** @vitest-environment jsdom */
/**
 * A turn the server starts by itself has no controller in this client; the server-reported status and the
 * chat-level cancel are all that reach it.
 *
 * Real scenario: a background subagent finishes while the chat is idle, the server wakes the agent, and the
 * user watches it run. The Stop button must know the turn is running and must cancel it by chat id.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cancelChatTurn, selectChatGenerating } from '@/store/chat/serverTurn';
import { cancelActiveChatAgent } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';

vi.mock('@/services/chat', () => ({
  cancelActiveChatAgent: vi.fn(),
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('selectChatGenerating', () => {
  it('is true only when the server reports the open chat as generating', () => {
    expect(selectChatGenerating({ chatId: 'chat-1', sessionStatuses: { 'chat-1': 'generating' } })).toBe(true);
  });

  it('ignores a turn running in another chat', () => {
    expect(selectChatGenerating({ chatId: 'chat-1', sessionStatuses: { 'chat-2': 'generating' } })).toBe(false);
  });

  it('is false while the chat waits for an approval, so an approval card keeps the focus', () => {
    expect(selectChatGenerating({ chatId: 'chat-1', sessionStatuses: { 'chat-1': 'awaiting_approval' } })).toBe(false);
  });

  it('is false without an open chat', () => {
    expect(selectChatGenerating({ chatId: undefined, sessionStatuses: { 'chat-1': 'generating' } })).toBe(false);
  });
});

describe('cancelChatTurn', () => {
  it('cancels the chat by id and reports success', async () => {
    vi.mocked(cancelActiveChatAgent).mockResolvedValue(undefined as never);

    await cancelChatTurn('chat-1');

    expect(cancelActiveChatAgent).toHaveBeenCalledWith('chat-1');
    expect(showI18nToast).toHaveBeenCalledWith('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
  });

  it('reports a failed cancel instead of throwing', async () => {
    vi.mocked(cancelActiveChatAgent).mockRejectedValue(new Error('404'));

    await expect(cancelChatTurn('chat-1')).resolves.toBeUndefined();

    expect(showI18nToast).toHaveBeenCalledWith('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
  });
});
