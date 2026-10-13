'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const CREATED_AT = new Date('2026-10-13T00:00:00.000Z');

function message(messageId: string, role: Message['role'], extra: Partial<Message> = {}): Message {
  return { messageId, chatId: 'chat-lta', role, content: `content of ${messageId}`, createdAt: CREATED_AT, ...extra };
}

const storeMessages = vi.hoisted(() => ({ current: [] as Message[] }));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({
        chatId: 'chat-lta',
        workspaceDir: undefined,
        messages: storeMessages.current,
        sendMessage: vi.fn(),
      }),
    {
      getState: () => ({ chatId: 'chat-lta', messages: storeMessages.current, sendMessage: vi.fn() }),
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
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock('@/components/features/message-box/MessageActionBar', () => ({
  default: ({ isLastTurnAnswer }: { isLastTurnAnswer: boolean }) => (
    <div data-testid="action-bar" data-last-turn-answer={String(isLastTurnAnswer)} />
  ),
}));
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

const CONVERSATION: Message[] = [
  message('u1', 'user'),
  message('a1', 'assistant'),
  message('u2', 'user'),
  message('a2', 'assistant'),
  message('n1', 'assistant', { isSystemNotice: true }),
];

function actionBarFlag(target: Message): string | null {
  storeMessages.current = CONVERSATION;
  const { container, unmount } = render(
    <MessageBox message={target} messageIndex={CONVERSATION.indexOf(target)} loading={false} isLast={false} />,
  );
  const flag = screen.queryByTestId('action-bar')?.getAttribute('data-last-turn-answer') ?? null;
  unmount();
  container.remove();
  return flag;
}

describe('MessageBox last-turn answer wiring', () => {
  it('lets only the answer of the latest turn offer regenerate', () => {
    expect(actionBarFlag(CONVERSATION[3])).toBe('true');
  });

  it('withholds it from an earlier turn that the server will not act on', () => {
    expect(actionBarFlag(CONVERSATION[1])).toBe('false');
  });

  it('withholds it from a system notice that follows the latest answer', () => {
    expect(actionBarFlag(CONVERSATION[4])).toBe('false');
  });
});
