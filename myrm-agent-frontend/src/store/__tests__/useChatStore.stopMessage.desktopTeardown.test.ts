/** @vitest-environment jsdom */
/**
 * stopMessage must release desktop + browser inspector turn engagement on cancel.
 *
 * Real scenario: user hits stop while the agent is driving desktop/browser tools.
 * The abort path bypasses MESSAGE_END, so the inspector "controlling" state would
 * otherwise stay stale until the next chat switch.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import type { Message } from '@/store/chat/types';

const mockDesktopReleaseTurnEngagement = vi.fn();
const mockBrowserReleaseTurnEngagement = vi.fn();

vi.mock('@/store/useDesktopInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockDesktopReleaseTurnEngagement }),
  },
}));

vi.mock('@/store/useBrowserInspectorStore', () => ({
  default: {
    getState: () => ({ releaseTurnEngagement: mockBrowserReleaseTurnEngagement }),
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
  mockDesktopReleaseTurnEngagement.mockClear();
  mockBrowserReleaseTurnEngagement.mockClear();
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

describe('stopMessage inspector teardown', () => {
  it('releases desktop and browser turn engagement on chat-level stop', async () => {
    const { stopMessage } = useChatStore.getState();

    stopMessage();

    await vi.waitFor(() => {
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledWith('chat-1');
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledWith('chat-1');
    });
  });

  it('releases desktop and browser turn engagement on pane-level stop', async () => {
    useWorkspaceStore.setState({
      panes: [{ chatId: 'chat-1', id: 'pane-1' } as never],
    });
    useWorkspaceStore.getState().setPaneAbortController('pane-1', new AbortController());
    useWorkspaceStore.getState().setPaneCurrentSessionMessageId('pane-1', 'msg-1');
    const { stopMessage } = useChatStore.getState();

    stopMessage();

    await vi.waitFor(() => {
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockDesktopReleaseTurnEngagement).toHaveBeenCalledWith('chat-1');
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledTimes(1);
      expect(mockBrowserReleaseTurnEngagement).toHaveBeenCalledWith('chat-1');
    });
  });
});
