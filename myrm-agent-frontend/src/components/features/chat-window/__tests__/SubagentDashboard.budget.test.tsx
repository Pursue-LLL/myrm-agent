/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SubagentNode } from '@/store/chat/useSubagentStore';

const withBudgetNode: SubagentNode = {
  task_id: 'task-with-budget',
  parent_task_id: '',
  agent_type: 'generalPurpose',
  description: 'Budgeted research',
  status: 'running',
  progress: 42,
  startedAt: Date.now() - 5000,
  budget: { budget_tokens: 50_000, max_cost_usd: 2.5, timeout_seconds: 300 },
  token_usage: { total_tokens: 1_000, total_cost_usd: 0.5 },
};

const withoutBudgetNode: SubagentNode = {
  task_id: 'task-without-budget',
  parent_task_id: '',
  agent_type: 'generalPurpose',
  description: 'Unbudgeted research',
  status: 'completed',
  progress: 100,
  token_usage: { total_tokens: 2_500, total_cost_usd: 1.2 },
};

const mockFetchWithTimeout = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

let mockSubagentState = {
  nodes: {} as Record<string, SubagentNode>,
  fissionBatch: null as null,
  setNodes: vi.fn(),
  completeNode: vi.fn(),
  clear: vi.fn(),
  dismissOvertime: vi.fn(),
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'chat-budget-e2e' })),
}));

vi.mock('@/store/chat/useSubagentStore', () => ({
  useSubagentStore: Object.assign(
    vi.fn((selector: (state: typeof mockSubagentState) => unknown) => selector(mockSubagentState)),
    { getState: () => mockSubagentState },
  ),
  isNodeOvertime: () => false,
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
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

describe('SubagentDashboard budget display', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubagentState = {
      nodes: {
        [withBudgetNode.task_id]: { ...withBudgetNode },
        [withoutBudgetNode.task_id]: { ...withoutBudgetNode },
      },
      fissionBatch: null,
      setNodes: vi.fn(),
      completeNode: vi.fn(),
      clear: vi.fn(),
      dismissOvertime: vi.fn(),
    };
    mockFetchWithTimeout.mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    });
  });

  it('shows used/limit for tokens and cost when a budget is set', async () => {
    const { default: SubagentDashboard } = await import('../SubagentDashboard');
    render(<SubagentDashboard chatId="chat-budget-e2e" />);

    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
    expect(await screen.findByTestId('subagent-dashboard-panel')).toBeTruthy();

    // 1,000 / 50,000 tokens rendered via fmtTokens: "1.0k/50k tok"
    expect(screen.getByText('1.0k/50k tok')).toBeTruthy();
    // $0.500 / $2.50 cost rendered as used/limit
    expect(screen.getByText('$0.500/2.50')).toBeTruthy();
  });

  it('shows absolute token count and cost when no budget is set', async () => {
    const { default: SubagentDashboard } = await import('../SubagentDashboard');
    render(<SubagentDashboard chatId="chat-budget-e2e" />);

    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
    expect(await screen.findByTestId('subagent-dashboard-panel')).toBeTruthy();

    // Without budget: plain token count
    expect(screen.getByText('2,500 tok')).toBeTruthy();
    // Without budget: plain cost
    expect(screen.getByText('$1.200')).toBeTruthy();
  });

  it('does not render NaN% when a node lacks progress data', async () => {
    mockSubagentState = {
      ...mockSubagentState,
      nodes: {
        [withBudgetNode.task_id]: { ...withBudgetNode, progress: undefined as unknown as number },
      },
    };
    const { default: SubagentDashboard } = await import('../SubagentDashboard');
    render(<SubagentDashboard chatId="chat-budget-e2e" />);

    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
    expect(await screen.findByTestId('subagent-dashboard-panel')).toBeTruthy();

    expect(screen.queryByText('NaN%')).toBeNull();
  });
});
