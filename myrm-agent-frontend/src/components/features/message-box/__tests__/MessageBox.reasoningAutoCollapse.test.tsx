'use client';

/**
 * 思考块折叠语义：
 * - 只在「思考 → 开始输出正文」这一次自动折叠（延迟 1s）；
 * - 折叠之后用户手动展开，不得再被自动收起（否则永远看不了历史思考）。
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const CREATED_AT = new Date('2026-10-13T00:00:00.000Z');

const storeMessages = vi.hoisted(() => ({ current: [] as Message[] }));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ chatId: 'chat-reason', messages: storeMessages.current, sendMessage: vi.fn() }),
    {
      getState: () => ({ chatId: 'chat-reason', messages: storeMessages.current, sendMessage: vi.fn() }),
      setState: vi.fn(),
    },
  ),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ enableEvalLab: false, reasoningDisplayMode: 'collapsed', personalSettings: {} }),
}));

vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/ConsensusThinkingPanel', () => ({ default: () => null }));
vi.mock('@/components/features/chat-window/approval/VisualApprovalInlineSection', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/ArtifactsDisplay', () => ({ default: () => null }));
vi.mock('@/components/features/artifacts/ArtifactErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div data-testid="md">{content}</div>,
}));
vi.mock('@/components/features/message-box/MessageActionBar', () => ({ default: () => null }));
vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: { getState: () => ({ fetchPlan: vi.fn() }) },
}));
vi.mock('@/components/features/message-box/Suggestions', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/QuoteToolbar', () => ({
  QuoteToolbar: () => null,
  useQuoteSelection: () => ({ state: null, dismiss: vi.fn() }),
}));
vi.mock('@/components/features/message-box/MemoryInsightPanel', () => ({ default: () => null }));
vi.mock('@/components/features/message-box/McpAppSection', () => ({ McpAppSection: () => null }));
vi.mock('@/services/chat', () => ({
  regenerateLastTurn: vi.fn(),
  cancelAgentRequest: vi.fn(),
  truncateAfterMessage: vi.fn(),
}));

function reasoningMessage(content: string): Message {
  return {
    messageId: 'a-reason',
    chatId: 'chat-reason',
    role: 'assistant',
    content,
    reasoning: '先分析需求再作答',
    reasoningStartedAt: CREATED_AT.getTime(),
    createdAt: CREATED_AT,
  };
}

describe('MessageBox reasoning auto-collapse', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('collapses once when the answer starts and lets the user reopen it afterwards', () => {
    vi.useFakeTimers();
    const thinking = reasoningMessage('');
    storeMessages.current = [thinking];

    const { rerender } = render(<MessageBox message={thinking} messageIndex={0} loading isLast />);
    expect(screen.getByText('先分析需求再作答')).toBeTruthy();

    const answered = reasoningMessage('这是回答');
    storeMessages.current = [answered];
    rerender(<MessageBox message={answered} messageIndex={0} loading={false} isLast />);

    expect(screen.getByText('先分析需求再作答')).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.queryByText('先分析需求再作答')).toBeNull();

    fireEvent.click(screen.getByLabelText('expandReasoning'));
    expect(screen.getByText('先分析需求再作答')).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText('先分析需求再作答')).toBeTruthy();
  });
});
