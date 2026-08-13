'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import MessageBox from '@/components/features/message-box/MessageBox';
import type { Message } from '@/store/chat/types';

const stableT = (key: string, params?: { count?: number }) => {
  if (key === 'message.workspaceMergeFailedTitle') {return 'Workspace Merge Failed';}
  if (key === 'message.workspaceMergeFailed') {return `${params?.count ?? 0} merge errors`;}
  if (key === 'message.workspaceMergeFailedMore') {return `${params?.count ?? 0} more hidden`;}
  if (key === 'message.workflowMergeWarning') {return 'Generic workflow merge warning';}
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({
        chatId: 'chat-wsmr',
        workspaceDir: undefined,
        messages: [],
        sendMessage: vi.fn(),
      }),
    {
      getState: () => ({
        chatId: 'chat-wsmr',
        messages: [],
        sendMessage: vi.fn(),
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

vi.mock('@/store/useCLIAgentStore', () => ({
  useCLIAgentStore: { getState: () => ({ respondPermission: vi.fn() }) },
}));

vi.mock('@/components/features/message-box/progress-steps/ProgressSteps', () => ({
  default: () => null,
}));
vi.mock('@/components/features/message-box/ConsensusThinkingPanel', () => ({
  default: () => null,
}));
vi.mock('@/components/features/chat-window/approval/VisualApprovalInlineSection', () => ({
  default: () => null,
}));
vi.mock('@/components/features/artifacts/ArtifactsDisplay', () => ({
  default: () => null,
}));
vi.mock('@/components/features/interactive-ui', () => ({
  InteractiveUIDisplay: () => null,
}));
vi.mock('@/components/features/artifacts/ArtifactErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/features/message-box/ToolCallApproval', () => ({
  default: () => null,
}));
vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}));
vi.mock('@/components/features/message-box/MessageActionBar', () => ({
  default: () => null,
}));
vi.mock('@/components/features/message-box/Suggestions', () => ({
  default: () => null,
}));
vi.mock('@/components/features/message-box/QuoteToolbar', () => ({
  QuoteToolbar: () => null,
  useQuoteSelection: () => ({ state: null, dismiss: vi.fn() }),
}));
vi.mock('@/components/features/message-box/MemoryInsightPanel', () => ({
  default: () => null,
}));
vi.mock('@/components/features/message-box/McpAppSection', () => ({
  McpAppSection: () => null,
}));
vi.mock('@/services/chat', () => ({
  regenerateLastTurn: vi.fn(),
  undoLastTurn: vi.fn(),
  cancelAgentRequest: vi.fn(),
  truncateAfterMessage: vi.fn(),
}));

const assistantMessage: Message = {
  messageId: 'msg-wsmr',
  chatId: 'chat-wsmr',
  role: 'assistant',
  content: 'Workspace merge E2E fixture answer.',
  createdAt: new Date('2026-08-04T00:00:00.000Z'),
  workspaceMergeFailures: [{ message: 'task_index=1: No space left on device' }],
  workspaceMergeFailedCount: 1,
  completionStatus: 'warning',
};

describe('MessageBox workspace merge warning', () => {
  it('renders WorkspaceMergeWarning in MessageBox tree (production path, not E2E fallback)', () => {
    render(
      <MessageBox
        message={assistantMessage}
        messageIndex={1}
        loading={false}
        isLast={true}
      />,
    );

    const panel = screen.getByTestId('workspace-merge-warning');
    expect(panel.getAttribute('data-e2e-merge-fallback')).toBeNull();
    expect(screen.getByText('Workspace Merge Failed')).toBeTruthy();

    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('task_index=1: No space left on device')).toBeTruthy();
    expect(screen.queryByText('Generic workflow merge warning')).toBeNull();
  });

  it('shows workspace merge warning while last message is still loading', () => {
    render(
      <MessageBox
        message={assistantMessage}
        messageIndex={1}
        loading={true}
        isLast={true}
      />,
    );

    expect(screen.getByTestId('workspace-merge-warning')).toBeTruthy();
  });
});
