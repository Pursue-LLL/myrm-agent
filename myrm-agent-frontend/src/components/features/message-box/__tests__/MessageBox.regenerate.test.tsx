'use client';

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const ASSISTANT: Message = {
  messageId: 'a1',
  chatId: 'chat-regen',
  role: 'assistant',
  content: 'content of a1',
  createdAt: new Date('2026-10-13T00:00:00.000Z'),
};

const mocks = vi.hoisted(() => ({
  regenerateLastTurn: vi.fn(),
  sendMessage: vi.fn(),
  onRegenerate: undefined as undefined | ((instruction?: string) => Promise<boolean>),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({
        chatId: 'chat-regen',
        workspaceDir: undefined,
        messages: [ASSISTANT],
        sendMessage: mocks.sendMessage,
      }),
    {
      getState: () => ({ chatId: 'chat-regen', messages: [ASSISTANT], sendMessage: mocks.sendMessage }),
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
  default: (props: { onRegenerate: (instruction?: string) => Promise<boolean> }) => {
    mocks.onRegenerate = props.onRegenerate;
    return null;
  },
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
  regenerateLastTurn: (...args: unknown[]) => mocks.regenerateLastTurn(...args),
  cancelAgentRequest: vi.fn(),
  truncateAfterMessage: vi.fn(),
}));

function regenerate(instruction?: string): Promise<boolean> {
  render(<MessageBox message={ASSISTANT} messageIndex={0} loading={false} isLast />);
  if (!mocks.onRegenerate) {
    throw new Error('the action bar never received onRegenerate');
  }
  return mocks.onRegenerate(instruction);
}

describe('MessageBox regenerate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.onRegenerate = undefined;
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('reports a refused request, so the menu keeps the instruction, and does not send a turn', async () => {
    mocks.regenerateLastTurn.mockRejectedValue(new Error('The text was held by a risk rule'));

    await expect(regenerate('use the key I pasted')).resolves.toBe(false);

    expect(mocks.regenerateLastTurn).toHaveBeenCalledWith('chat-regen', 'use the key I pasted');
    expect(mocks.sendMessage).not.toHaveBeenCalled();
  });

  it('reports a turn that was not dispatched', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: true, query: 'summarise the report' });
    mocks.sendMessage.mockResolvedValue(false);

    await expect(regenerate('be concise')).resolves.toBe(false);
  });

  it('reports a regeneration without a query to send', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: false });

    await expect(regenerate()).resolves.toBe(false);
    expect(mocks.sendMessage).not.toHaveBeenCalled();
  });

  it('reports a regeneration whose turn was dispatched', async () => {
    mocks.regenerateLastTurn.mockResolvedValue({ success: true, query: 'summarise the report' });
    mocks.sendMessage.mockResolvedValue(true);

    await expect(regenerate('be concise')).resolves.toBe(true);
    expect(mocks.sendMessage).toHaveBeenCalledWith('summarise the report');
  });
});
