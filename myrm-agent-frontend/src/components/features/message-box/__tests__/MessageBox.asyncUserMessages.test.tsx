'use client';

import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const mockSteerMessage = vi.fn().mockResolvedValue(true);
const mockSetInputMessage = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh-CN',
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({
        chatId: 'chat-async-msg',
        workspaceDir: undefined,
        messages: [],
        enabledBuiltinTools: [],
        currentBuiltinTools: [],
        sendMessage: vi.fn(),
      }),
    {
      getState: () => ({
        chatId: 'chat-async-msg',
        messages: [],
        enabledBuiltinTools: [],
        currentBuiltinTools: [],
        sendMessage: vi.fn(),
        steerMessage: mockSteerMessage,
        setInputMessage: mockSetInputMessage,
        setState: vi.fn(),
      }),
      setState: vi.fn(),
    },
  ),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      enableEvalLab: false,
      reasoningDisplayMode: 'collapsed',
      personalSettings: {},
    }),
}));

vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({
  default: () => null,
}));

vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div data-testid="markdown-content">{content}</div>,
}));

describe('MessageBox AsyncAgentMessageCard integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const baseAssistantMessage: Message = {
    messageId: 'msg-assistant-async-1',
    chatId: 'chat-async-msg',
    createdAt: new Date(),
    role: 'assistant',
    content: 'Running financial analysis...',
    asyncUserMessages: [
      {
        callId: 'call_clarify_gaap_1',
        message: 'Ambiguity found between GAAP and Non-GAAP metrics.',
        category: 'question',
        recommendation: 'Proceed with Non-GAAP standard metrics',
      },
    ],
  };

  it('renders AsyncAgentMessageCard when message.asyncUserMessages has entries', () => {
    render(
      <MessageBox message={baseAssistantMessage} messageIndex={1} isLast={true} loading={true} />,
    );

    expect(screen.getByText('Ambiguity found between GAAP and Non-GAAP metrics.')).toBeInTheDocument();
    expect(screen.getByText('Proceed with Non-GAAP standard metrics')).toBeInTheDocument();
  });

  it('triggers steerMessage when user adopts recommendation while streaming', async () => {
    render(
      <MessageBox message={baseAssistantMessage} messageIndex={1} isLast={true} loading={true} />,
    );

    const adoptBtn = screen.getByRole('button', { name: /采纳/i });
    await act(async () => {
      fireEvent.click(adoptBtn);
    });

    expect(mockSteerMessage).toHaveBeenCalledWith('Proceed with Non-GAAP standard metrics', {
      inReplyToCallId: 'call_clarify_gaap_1',
      questionContext: 'Ambiguity found between GAAP and Non-GAAP metrics.',
    });
    expect(mockSetInputMessage).not.toHaveBeenCalled();
  });

  it('falls back to setInputMessage (Hermes #64578) when turn already completed', async () => {
    render(
      <MessageBox message={baseAssistantMessage} messageIndex={1} isLast={true} loading={false} />,
    );

    const adoptBtn = screen.getByRole('button', { name: /采纳/i });
    await act(async () => {
      fireEvent.click(adoptBtn);
    });

    expect(mockSteerMessage).not.toHaveBeenCalled();
    expect(mockSetInputMessage).toHaveBeenCalledWith('Proceed with Non-GAAP standard metrics');
  });

  it('triggers steerMessage when user clicks suggested reply chip while streaming', async () => {
    const messageWithChips: Message = {
      messageId: 'msg-assistant-async-2',
      chatId: 'chat-async-msg',
      createdAt: new Date(),
      role: 'assistant',
      content: 'Configuring cache...',
      asyncUserMessages: [
        {
          callId: 'call_clarify_cache_1',
          message: 'Choose cache backend',
          category: 'question',
          suggested_replies: ['Redis', 'Memcached'],
        },
      ],
    };

    render(
      <MessageBox message={messageWithChips} messageIndex={1} isLast={true} loading={true} />,
    );

    expect(screen.getByText('Choose cache backend')).toBeInTheDocument();
    expect(screen.getByText('Redis')).toBeInTheDocument();
    expect(screen.getByText('Memcached')).toBeInTheDocument();

    const redisBtn = screen.getByRole('button', { name: 'Redis' });
    await act(async () => {
      fireEvent.click(redisBtn);
    });

    expect(mockSteerMessage).toHaveBeenCalledWith('Redis', {
      inReplyToCallId: 'call_clarify_cache_1',
      questionContext: 'Choose cache backend',
    });
  });
});
