import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReplayDeterminismResponse } from '@/services/chat';
import { deferred } from '@/test-utils/deferred';

import ChatSessionHeader, { type ChatWindowTab } from '../ChatSessionHeader';

const kit = vi.hoisted(() => ({
  replayChatSession: vi.fn<(chatId: string) => Promise<unknown>>(),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  replayChatSession: kit.replayChatSession,
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('../TrajectoryDiffModal', () => ({ default: () => null }));
vi.mock('../ParentChatLink', () => ({
  ParentChatLink: ({ chatId }: { chatId: string }) => <div data-testid="parent-link">{chatId}</div>,
}));
vi.mock('../ChatCronLink', () => ({
  ChatCronLink: ({ chatId }: { chatId: string }) => <div data-testid="cron-link">{chatId}</div>,
}));
vi.mock('../SessionExportButton', () => ({
  default: ({ chatId }: { chatId: string }) => <div data-testid="export-button">{chatId}</div>,
}));
vi.mock('../DashboardWorkspaceLink', () => ({
  DashboardWorkspaceLink: () => <div data-testid="workspace-link" />,
}));
vi.mock('@/components/features/message-actions/SessionRevertButton', () => ({
  default: ({ sessionId }: { sessionId: string }) => <div data-testid="revert-button">{sessionId}</div>,
}));

const replayResult = (score: number): ReplayDeterminismResponse => ({
  session_id: 'chat',
  determinism_score: score,
  tool_sequence_similarity: score,
  tool_set_jaccard: score,
  args_similarity: score,
  original_tool_count: 1,
  replayed_tool_count: 1,
  drifted_tools: [],
  verdict: 'DETERMINISTIC',
});

function header(
  chatId: string,
  activeTab: ChatWindowTab = 'chat',
  onTabChange: (tab: ChatWindowTab) => void = vi.fn(),
) {
  return <ChatSessionHeader chatId={chatId} activeTab={activeTab} onTabChange={onTabChange} />;
}

const replayButton = () => screen.getByRole('button', { name: /Verify(ing)? Replay/ });
const scoreBadge = () => screen.queryByTitle('Click to inspect trajectory differences');
const chatTab = () => screen.getByRole('button', { name: 'Chat' });
const traceTab = () => screen.getByRole('button', { name: 'Trace' });

beforeEach(() => {
  vi.resetAllMocks();
});

describe('ChatSessionHeader', () => {
  it('hands the chat to every entry that belongs to it', () => {
    render(header('chat-a'));

    expect(screen.getByTestId('parent-link')).toHaveTextContent('chat-a');
    expect(screen.getByTestId('cron-link')).toHaveTextContent('chat-a');
    expect(screen.getByTestId('revert-button')).toHaveTextContent('chat-a');
    expect(screen.getByTestId('export-button')).toHaveTextContent('chat-a');
    expect(screen.getByTestId('workspace-link')).toBeInTheDocument();
    expect(replayButton()).toBeInTheDocument();
  });

  it.each([
    ['chat', true, false],
    ['trace', false, true],
  ] as const)('marks only the %s tab as pressed while it is active', (activeTab, chatPressed, tracePressed) => {
    render(header('chat-a', activeTab));

    expect(chatTab()).toHaveAttribute('aria-pressed', String(chatPressed));
    expect(traceTab()).toHaveAttribute('aria-pressed', String(tracePressed));
  });

  it('reports the tab the user picks, the active one included', () => {
    const onTabChange = vi.fn();
    render(header('chat-a', 'chat', onTabChange));

    fireEvent.click(traceTab());
    fireEvent.click(chatTab());

    expect(onTabChange.mock.calls).toEqual([['trace'], ['chat']]);
  });

  it('does not carry a replay score over to another chat', async () => {
    kit.replayChatSession.mockResolvedValue(replayResult(1));
    const { rerender } = render(header('chat-a'));
    await act(async () => fireEvent.click(replayButton()));
    expect(kit.replayChatSession).toHaveBeenCalledExactlyOnceWith('chat-a');
    expect(scoreBadge()).toHaveTextContent('100% Match');

    rerender(header('chat-b'));

    expect(scoreBadge()).toBeNull();
    expect(replayButton()).toBeEnabled();
    expect(screen.getByTestId('export-button')).toHaveTextContent('chat-b');
  });

  it('shows the score again for the chat that was replayed only when it is replayed again', async () => {
    kit.replayChatSession.mockResolvedValue(replayResult(1));
    const { rerender } = render(header('chat-a'));
    await act(async () => fireEvent.click(replayButton()));

    rerender(header('chat-b'));
    rerender(header('chat-a'));

    expect(scoreBadge()).toBeNull();
  });

  it('leaves the next chat idle when a replay is still running as the user leaves', async () => {
    const pending = deferred<ReplayDeterminismResponse>();
    kit.replayChatSession.mockReturnValue(pending.promise);
    const { rerender } = render(header('chat-a'));
    fireEvent.click(replayButton());
    expect(replayButton()).toBeDisabled();

    rerender(header('chat-b'));
    expect(replayButton()).toBeEnabled();
    expect(replayButton()).toHaveTextContent('Verify Replay');
    await act(async () => pending.resolve(replayResult(1)));

    expect(scoreBadge()).toBeNull();
    expect(replayButton()).toBeEnabled();
  });

  it('keeps the entries of the same chat when only the tab changes', async () => {
    kit.replayChatSession.mockResolvedValue(replayResult(1));
    const { rerender } = render(header('chat-a', 'chat'));
    await act(async () => fireEvent.click(replayButton()));

    rerender(header('chat-a', 'trace'));

    expect(scoreBadge()).toHaveTextContent('100% Match');
  });
});
