/**
 * The subagent panel shows the subagents of the chat the user has open, and says so in the user's language when a
 * control fails.
 *
 * Real scenario: the user works with subagents in chat A, then opens another chat; "new chat" is another chat too, a
 * fresh session with an id of its own. The panel must empty at once, while an id that merely arrives where there was
 * none leaves what the stream put there alone.
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

  it('empties the panel when "new chat" is pressed, which opens a session with its own id', () => {
    const view = render(<SubagentDashboard chatId="chat-a" />);
    useSubagentStore.getState().setNodes([runningNode('task-of-a')]);

    openChat('chat-new-session');
    view.rerender(<SubagentDashboard chatId={undefined} />);

    expect(nodeIds()).toEqual([]);
  });

  it('empties the panel when the open chat id goes away', () => {
    const view = render(<SubagentDashboard chatId="chat-a" />);
    useSubagentStore.getState().setNodes([runningNode('task-of-a')]);

    openChat(undefined);
    view.rerender(<SubagentDashboard chatId={undefined} />);

    expect(nodeIds()).toEqual([]);
  });

  it("brings a chat's subagents back from the server when the user returns to it", async () => {
    // While the user was elsewhere the chat's stream wrote nothing into the tree, so the server is the source.
    fetchMock.mockImplementation(async (url: string) =>
      url === '/chats/chat-a/subagents'
        ? jsonResponse({ data: [runningNode('task-of-a')] })
        : jsonResponse({ data: [] }),
    );
    const view = render(<SubagentDashboard chatId="chat-a" />);
    await waitFor(() => expect(nodeIds()).toEqual(['task-of-a']));

    openChat('chat-b');
    view.rerender(<SubagentDashboard chatId="chat-b" />);
    expect(nodeIds()).toEqual([]);

    openChat('chat-a');
    view.rerender(<SubagentDashboard chatId="chat-a" />);
    // Within the 2s poll interval: returning to the chat fetches at once, it does not wait for the next poll.
    await waitFor(() => expect(nodeIds()).toEqual(['task-of-a']), { timeout: 500 });
  });

  it('keeps what the stream put in the panel when an id arrives where there was none', () => {
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
