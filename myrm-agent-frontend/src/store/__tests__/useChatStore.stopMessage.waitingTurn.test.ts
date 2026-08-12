/** @vitest-environment jsdom */
/**
 * stopMessage must remove the waiting_for_turn progress step on cancel.
 *
 * Real scenario: user hits stop (input stop button / mobile stop / pane stop)
 * while a turn is queued on a held project lock. The backend pump aborts on
 * cancel without emitting waiting_for_turn_clear, so the frontend must clear
 * the stale waiting step synchronously or the UI keeps showing it forever.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import type { Message, ProgressItem } from '@/store/chat/types';

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    cancelAgentRequest: vi.fn().mockResolvedValue(undefined),
    cancelActiveChatAgent: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

function makeAssistantMessage(messageId: string, withWaiting: boolean): Message {
  const progressSteps: ProgressItem[] = withWaiting
    ? [{ step_key: 'waiting_for_turn', status: undefined }]
    : [];
  return {
    messageId,
    chatId: 'chat-1',
    role: 'assistant',
    content: '',
    createdAt: new Date('2026-08-04T00:00:00.000Z'),
    progressSteps,
  };
}

function findWaitingStep(messages: Message[], messageId: string): boolean {
  const msg = messages.find((m) => m.messageId === messageId);
  return Boolean(msg?.progressSteps?.some((s) => String(s.step_key) === 'waiting_for_turn'));
}

beforeEach(() => {
  useChatStore.setState({
    chatId: 'chat-1',
    currentSessionMessageId: 'msg-1',
    messages: [makeAssistantMessage('msg-1', true)],
    loading: true,
    abortController: new AbortController(),
    messageAppeared: false,
  });
  useWorkspaceStore.setState({ panes: [] });
});

describe('stopMessage waiting_for_turn cleanup', () => {
  it('chat-level stop clears the waiting step and aborts the controller', () => {
    const { stopMessage } = useChatStore.getState();
    const before = useChatStore.getState().abortController;
    expect(findWaitingStep(useChatStore.getState().messages, 'msg-1')).toBe(true);

    stopMessage();

    expect(findWaitingStep(useChatStore.getState().messages, 'msg-1')).toBe(false);
    expect(before?.signal.aborted).toBe(true);
    expect(useChatStore.getState().loading).toBe(false);
    expect(useChatStore.getState().abortController).toBeNull();
  });

  it('clears the waiting step without touching other messages', () => {
    useChatStore.setState({
      messages: [
        makeAssistantMessage('msg-1', true),
        makeAssistantMessage('msg-2', true),
      ],
    });
    const { stopMessage } = useChatStore.getState();

    stopMessage();

    // 仅当前 session message 被清理，其他消息保留自己的 waiting 步骤
    expect(findWaitingStep(useChatStore.getState().messages, 'msg-1')).toBe(false);
    expect(findWaitingStep(useChatStore.getState().messages, 'msg-2')).toBe(true);
  });

  it('is a no-op when there is no active chat', () => {
    useChatStore.setState({ chatId: undefined });
    const { stopMessage } = useChatStore.getState();

    stopMessage();

    // 无 chat → 不抛异常、状态不变
    expect(useChatStore.getState().chatId).toBeUndefined();
  });
});
