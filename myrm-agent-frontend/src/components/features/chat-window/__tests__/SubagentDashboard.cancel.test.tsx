/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SubagentNode } from '@/store/chat/useSubagentStore';

const runningNode: SubagentNode = {
  task_id: 'task-cancel-e2e',
  agent_type: 'generalPurpose',
  description: 'Research competitor pricing',
  status: 'running',
  progress: 42,
  startedAt: Date.now() - 5000,
};

const mockFetchWithTimeout = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

let mockSubagentState = {
  nodes: { [runningNode.task_id]: runningNode } as Record<string, SubagentNode>,
  fissionBatch: null as null,
  setNodes: vi.fn(),
  completeNode: vi.fn(),
  clear: vi.fn(),
  dismissOvertime: vi.fn(),
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'chat-cancel-e2e' })),
}));

vi.mock('@/store/chat/useSubagentStore', () => ({
  useSubagentStore: Object.assign(
    vi.fn((selector: (state: typeof mockSubagentState) => unknown) => selector(mockSubagentState)),
    { getState: () => mockSubagentState },
  ),
  isNodeOvertime: () => false,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => mockFetchWithTimeout(...args),
}));

vi.mock('sonner', () => ({
  toast: { success: (...args: unknown[]) => mockToastSuccess(...args), error: (...args: unknown[]) => mockToastError(...args) },
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../AgentToolDiagnostics', () => ({
  AgentToolDiagnostics: () => null,
}));

describe('SubagentDashboard cancel flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubagentState = {
      nodes: { [runningNode.task_id]: { ...runningNode } },
      fissionBatch: null,
      setNodes: vi.fn(),
      completeNode: vi.fn(),
      clear: vi.fn(),
      dismissOvertime: vi.fn(),
    };
    mockFetchWithTimeout.mockResolvedValue({
      ok: true,
      json: async () => ({ data: { cancelled: true } }),
    });
  });

  it('opens dashboard, confirms cancel, calls API and updates store', async () => {
    const { default: SubagentDashboard } = await import('../SubagentDashboard');
    render(<SubagentDashboard chatId="chat-cancel-e2e" />);

    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
    expect(await screen.findByTestId('subagent-dashboard-panel')).toBeTruthy();

    fireEvent.click(screen.getByTestId('subagent-cancel-btn'));
    fireEvent.click(screen.getByText('cancelConfirmAction'));

    await waitFor(() => {
      expect(mockFetchWithTimeout).toHaveBeenCalledWith(
        '/chats/chat-cancel-e2e/subagents/task-cancel-e2e/cancel',
        { method: 'POST' },
      );
    });
    expect(mockSubagentState.completeNode).toHaveBeenCalledWith('task-cancel-e2e', 'cancelled');
    expect(mockToastSuccess).toHaveBeenCalledWith('cancelSuccess');
  });
});
