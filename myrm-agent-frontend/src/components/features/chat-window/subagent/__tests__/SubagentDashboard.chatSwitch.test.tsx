/**
 * The subagent panel shows the subagents of the chat the user has open, and says so in the user's language when a
 * control fails.
 *
 * Real scenario: the user works with subagents in chat A, then opens another chat or presses "new chat". The panel must
 * empty at once, in either case, while a chat that merely receives its id on its first message keeps what it has.
 * When "stop all" is refused, the toast reads like the rest of the product instead of echoing the server's English.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock, toastError, toastSuccess } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }));
vi.mock('../../AgentToolDiagnostics', () => ({ AgentToolDiagnostics: () => null }));
vi.mock('../AgentWorkMap', () => ({ default: () => null }));
vi.mock('../SubagentInsightsView', () => ({ SubagentInsightsView: () => null }));
vi.mock('../SubagentDetailDrawer', () => ({ SubagentDetailDrawer: () => null }));

import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { SubagentDashboard } from '../SubagentDashboard';

const runningNode = (taskId: string): SubagentNode => ({
  task_id: taskId,
  parent_task_id: '',
  agent_type: 'researcher',
  description: 'Compare vendors',
  status: 'running',
  progress: 10,
});

const nodeIds = () => Object.keys(useSubagentStore.getState().nodes);

const jsonResponse = (body: unknown, ok = true) => ({ ok, json: async () => body });

function openChat(chatId: string | undefined): void {
  useChatStore.setState({ chatId });
}

describe('SubagentDashboard when the open chat changes', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse({ data: [] }));
    toastError.mockReset();
    toastSuccess.mockReset();
    openChat('chat-a');
  });

  it('empties the panel when another chat is opened', () => {
    const view = render(<SubagentDashboard chatId="chat-a" />);
    useSubagentStore.getState().setNodes([runningNode('task-of-a')]);

    openChat('chat-b');
    view.rerender(<SubagentDashboard chatId="chat-b" />);

    expect(nodeIds()).toEqual([]);
  });

  it('empties the panel when "new chat" is pressed', () => {
    const view = render(<SubagentDashboard chatId="chat-a" />);
    useSubagentStore.getState().setNodes([runningNode('task-of-a')]);

    openChat(undefined);
    view.rerender(<SubagentDashboard chatId={undefined} />);

    expect(nodeIds()).toEqual([]);
  });

  it('keeps the subagents of a new chat when its id arrives with the first message', () => {
    openChat(undefined);
    const view = render(<SubagentDashboard chatId={undefined} />);
    useSubagentStore.getState().setNodes([runningNode('task-of-new-chat')]);

    openChat('chat-new');
    view.rerender(<SubagentDashboard chatId="chat-new" />);

    expect(nodeIds()).toEqual(['task-of-new-chat']);
  });
});

describe('SubagentDashboard controls that the server refuses', () => {
  const refuse = (message: string) =>
    fetchMock.mockImplementation(async (_url: string, init?: { method?: string }) =>
      init?.method === 'POST' ? jsonResponse({ message }, false) : jsonResponse({ data: [] }),
    );

  beforeEach(() => {
    useSubagentStore.getState().clear();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse({ data: [] }));
    toastError.mockReset();
    openChat('chat-a');
    useSubagentStore.getState().setNodes([runningNode('task-of-a')]);
    render(<SubagentDashboard chatId="chat-a" />);
    fireEvent.click(screen.getByTestId('subagent-dashboard-trigger'));
  });

  it('tells the user "stop all" failed in the product language, not in the words of the server', async () => {
    refuse('No running subagents found for chat session chat-a.');

    fireEvent.click(screen.getByTestId('subagent-stop-all-btn'));
    fireEvent.click(await screen.findByText('stopAllConfirmAction'));

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError).toHaveBeenCalledWith('stopAllFailed');
  });

  it('tells the user pausing delegation failed in the product language, not in the words of the server', async () => {
    refuse('Delegation gate is unavailable for this session.');

    fireEvent.click(screen.getByTestId('delegation-pause-toggle'));

    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    expect(toastError).toHaveBeenCalledWith('delegationPauseFailed');
  });
});
