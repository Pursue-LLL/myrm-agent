/** @vitest-environment jsdom */
/**
 * stopMessage must release desktop inspector turn engagement on cancel.
 *
 * Real scenario: user hits stop while the agent is driving desktop tools. The
 * abort path bypasses MESSAGE_END, so the desktop inspector "controlling" state
 * would otherwise stay stale until the next chat switch.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import type { Message } from '@/store/chat/types';

const mockReleaseTurnEngagement = vi.fn();

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockReleaseTurnEngagement }),
  },
}));

vi.mock('@/services/chat', () => ({
  cancelAgentRequest: vi.fn().mockResolvedValue(undefined),
  cancelActiveChatAgent: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

function makeAssistantMessage(messageId: string): Message {
  return {
    messageId,
    chatId: 'chat-1',
    role: 'assistant',
    content: '',
    createdAt: new Date('2026-08-04T00:00:00.000Z'),
  };
}

beforeEach(() => {
  mockReleaseTurnEngagement.mockClear();
  useChatStore.setState({
    chatId: 'chat-1',
    currentSessionMessageId: 'msg-1',
    messages: [makeAssistantMessage('msg-1')],
    loading: true,
    abortController: new AbortController(),
    messageAppeared: false,
  });
  useWorkspaceStore.setState({ panes: [] });
});

describe('stopMessage desktop inspector teardown', () => {
  it('releases desktop turn engagement on chat-level stop', async () => {
    const { stopMessage } = useChatStore.getState();

    stopMessage();

    await vi.waitFor(() => {
      expect(mockReleaseTurnEngagement).toHaveBeenCalledTimes(1);
    });
  });
});
