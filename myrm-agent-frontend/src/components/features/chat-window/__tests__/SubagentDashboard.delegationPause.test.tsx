/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SubagentNode } from '@/store/chat/useSubagentStore';

const runningNode: SubagentNode = {
  task_id: 'task-pause-e2e',
  agent_type: 'generalPurpose',
  description: 'Long running worker',
  status: 'running',
  progress: 10,
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
  default: vi.fn((selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'chat-pause-e2e' })),
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

describe('SubagentDashboard delegation pause flow', () => {
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
    mockFetchWithTimeout.mockImplementation(async (url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.endsWith('/delegation/status')) {
        return { ok: true, json: async () => ({ data: { paused: false } }) };
      }
      if (typeof url === 'string' && url.endsWith('/delegation/pause') && init?.method === 'POST') {
        return { ok: true, json: async () => ({ data: { paused: true } }) };
      }
      if (typeof url === 'string' && url.endsWith('/subagents') && (!init || init.method === 'GET')) {
        return { ok: true, json: async () => ({ data: [runningNode] }) };
      }
      return { ok: true, json: async () => ({ data: {} }) };
    });
  });

  it('toggles delegation pause via dashboard control', async () => {
    const { default: SubagentDashboard } = await import('../SubagentDashboard');
    render(<SubagentDashboard chatId="chat-pause-e2e" />);

    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
    expect(await screen.findByTestId('subagent-dashboard-panel')).toBeTruthy();

    fireEvent.click(screen.getByTestId('delegation-pause-toggle'));

    await waitFor(() => {
      expect(mockFetchWithTimeout).toHaveBeenCalledWith(
        '/chats/chat-pause-e2e/subagents/delegation/pause',
        { method: 'POST' },
      );
    });
    expect(mockToastSuccess).toHaveBeenCalledWith('delegationPauseSuccess');
  });
});
