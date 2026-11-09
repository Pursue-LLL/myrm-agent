'use client';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message, Source } from '@/store/chat/types';

const CREATED_AT = new Date('2026-11-08T00:00:00.000Z');

function page(index: number, name: string): Source {
  return { index, type: 'web_search', title: name, url: `https://${name}.example/page` };
}

function turn(messageId: string, role: Message['role'], sources?: Source[]): Message {
  return { messageId, chatId: 'chat-cite', role, content: `content of ${messageId}`, createdAt: CREATED_AT, sources };
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
        chatId: 'chat-cite',
        workspaceDir: undefined,
        messages: storeMessages.current,
        sendMessage: vi.fn(),
      }),
    {
      getState: () => ({ chatId: 'chat-cite', messages: storeMessages.current, sendMessage: vi.fn() }),
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
  default: ({ sources }: { sources: Source[] }) => (
    <div data-testid="markdown" data-sources={sources.map((source) => `${source.index}:${source.title}`).join(',')} />
  ),
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

/** The sources MessageBox hands to the markdown of `conversation[at]`, as `number:title` in the order given. */
function citationSourcesOf(conversation: Message[], at: number): string[] {
  storeMessages.current = conversation;
  const { container, unmount } = render(
    <MessageBox message={conversation[at]} messageIndex={at} loading={false} isLast={false} />,
  );
  const handed = screen.getByTestId('markdown').getAttribute('data-sources') ?? '';
  unmount();
  container.remove();
  return handed ? handed.split(',') : [];
}

describe('MessageBox citation sources', () => {
  // The second turn numbered one of its pages 1 again (a run that restarted its numbering) and found a third page.
  const RESTARTED = [
    turn('u1', 'user'),
    turn('a1', 'assistant', [page(1, 'first-one'), page(2, 'first-two')]),
    turn('u2', 'user'),
    turn('a2', 'assistant', [page(1, 'second-one'), page(3, 'second-three')]),
  ];

  it('hands the markdown the own source of a number before an earlier message that has the same number', () => {
    expect(citationSourcesOf(RESTARTED, 3)).toEqual(['1:second-one', '2:first-two', '3:second-three']);
  });

  it('keeps an earlier message to the sources of the messages before it', () => {
    expect(citationSourcesOf(RESTARTED, 1)).toEqual(['1:first-one', '2:first-two']);
  });

  it('hands an answer without sources the nearest earlier message that has each number', () => {
    const conversation = [...RESTARTED, turn('u3', 'user'), turn('a3', 'assistant')];

    expect(citationSourcesOf(conversation, 5)).toEqual(['1:second-one', '2:first-two', '3:second-three']);
  });
});
