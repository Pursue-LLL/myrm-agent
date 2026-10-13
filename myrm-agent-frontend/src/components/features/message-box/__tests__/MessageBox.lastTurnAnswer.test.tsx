'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const CREATED_AT = new Date('2026-10-13T00:00:00.000Z');

function message(messageId: string, role: Message['role'], extra: Partial<Message> = {}): Message {
  return { messageId, chatId: 'chat-lta', role, content: `content of ${messageId}`, createdAt: CREATED_AT, ...extra };
}

const storeMessages = vi.hoisted(() => ({ current: [] as Message[] }));
const setStateMock = vi.hoisted(() => vi.fn());
const undoLastTurnMock = vi.hoisted(() => vi.fn());

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
      setState: setStateMock,
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
  default: ({ isLastTurnAnswer, onUndo }: { isLastTurnAnswer: boolean; onUndo: () => void }) => (
    <div data-testid="action-bar" data-last-turn-answer={String(isLastTurnAnswer)}>
      <button type="button" data-testid="stub-undo" onClick={onUndo}>
        undo
      </button>
    </div>
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
  undoLastTurn: undoLastTurnMock,
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
  it('lets only the answer of the latest turn offer retry and undo', () => {
    expect(actionBarFlag(CONVERSATION[3])).toBe('true');
  });

  it('withholds them from an earlier turn that the server will not act on', () => {
    expect(actionBarFlag(CONVERSATION[1])).toBe('false');
  });

  it('withholds them from a system notice that follows the latest answer', () => {
    expect(actionBarFlag(CONVERSATION[4])).toBe('false');
  });
});

describe('MessageBox undo from the latest answer', () => {
  it('removes the whole latest turn, notice included, and keeps the earlier turn', async () => {
    storeMessages.current = CONVERSATION;
    undoLastTurnMock.mockResolvedValue({ success: true, deleted_count: 3 });
    render(<MessageBox message={CONVERSATION[3]} messageIndex={3} loading={false} isLast={false} />);

    fireEvent.click(screen.getByTestId('stub-undo'));

    await waitFor(() => expect(setStateMock).toHaveBeenCalledTimes(1));
    expect(undoLastTurnMock).toHaveBeenCalledWith('chat-lta');
    const updater = setStateMock.mock.calls[0][0] as (state: { messages: Message[] }) => { messages: Message[] };
    expect(updater({ messages: CONVERSATION }).messages.map((m) => m.messageId)).toEqual(['u1', 'a1']);
  });
});
