import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ToolApprovalRequest } from '@/store/chat/types';
import useToolApprovalStore from '@/store/useToolApprovalStore';

import ToolApprovalDialog from '../ToolApprovalDialog';
import { approvalRequest, kit } from './approvalKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('sonner', async () => (await import('./approvalKit')).sonnerMock());
vi.mock('@/lib/approval/resumeApprovalStream', async (importOriginal) =>
  (await import('./approvalKit')).resumeMock(await importOriginal()),
);
vi.mock('../SingleApprovalCard', () => ({
  default: ({
    request,
    onResolve,
    isLoading,
  }: {
    request: ToolApprovalRequest;
    onResolve: (requestId: string, decision: 'approve' | 'reject') => Promise<void>;
    isLoading: boolean;
  }) => (
    <div data-testid="card" data-loading={isLoading}>
      {request.requestId}
      <button type="button" onClick={() => void onResolve(request.requestId, 'approve')}>
        approve {request.requestId}
      </button>
    </div>
  ),
}));

const show = (...requests: ToolApprovalRequest[]) => act(() => useToolApprovalStore.setState({ queue: requests }));
const dialog = () => screen.queryByRole('dialog');
const cardIds = () => screen.queryAllByTestId('card').map((card) => card.firstChild?.textContent);
const decisions = (call = 0) =>
  (kit.resume.mock.calls[call][1] as { decisions: Array<{ type: string; feedback?: string }> }).decisions;

beforeEach(() => {
  vi.resetAllMocks();
  kit.resume.mockResolvedValue(undefined);
  useToolApprovalStore.setState({ queue: [], batchDecisions: new Map(), isResolving: false });
});

describe('ToolApprovalDialog contents', () => {
  it('stays away while nothing waits for an answer', () => {
    render(<ToolApprovalDialog />);

    expect(dialog()).toBeNull();
  });

  it('leaves approvals that are answered on the page itself to the page', () => {
    render(<ToolApprovalDialog />);

    show(approvalRequest({ requestId: 'click', toolName: 'browser_click' }));
    expect(dialog()).toBeNull();

    show(approvalRequest({ requestId: 'click', toolName: 'browser_click' }), approvalRequest({ requestId: 'shell' }));
    expect(cardIds()).toEqual(['shell']);
    expect(within(dialog() as HTMLElement).getByText('Tool Execution Approval')).toBeInTheDocument();
  });

  it('asks about one approval with the plain title and no bulk buttons', () => {
    render(<ToolApprovalDialog />);

    show(approvalRequest());

    const open = within(dialog() as HTMLElement);
    expect(open.getByText('Tool Execution Approval')).toBeInTheDocument();
    expect(open.getByText(/^The agent wants to execute the following action/)).toBeInTheDocument();
    expect(cardIds()).toEqual(['req-1']);
    expect(open.queryByRole('button', { name: /Approve All|Reject All/ })).toBeNull();
  });

  it('words a hand-over differently from an approval, and only when every card is one', () => {
    render(<ToolApprovalDialog />);

    show(approvalRequest({ displayMode: 'handover' }));
    expect(within(dialog() as HTMLElement).getByText('Waiting for You')).toBeInTheDocument();
    expect(within(dialog() as HTMLElement).getByText(/^The agent needs you to complete an action/)).toBeInTheDocument();

    show(approvalRequest({ displayMode: 'handover' }), approvalRequest({ requestId: 'req-2', messageId: 'msg-2' }));
    expect(within(dialog() as HTMLElement).queryByText('Waiting for You')).toBeNull();
    expect(within(dialog() as HTMLElement).getByText('Batch Approval (2 tools)')).toBeInTheDocument();
    expect(
      within(dialog() as HTMLElement).getByText(/^The agent wants to execute the following action/),
    ).toBeInTheDocument();
  });

  it('puts the cards of one batch in a labelled group in batch order, ahead of the single cards', () => {
    render(<ToolApprovalDialog />);

    show(
      approvalRequest({ requestId: 'single', messageId: 'msg-3' }),
      approvalRequest({ requestId: 'b2', batchId: 'batch', batchIndex: 1 }),
      approvalRequest({ requestId: 'b1', batchId: 'batch', batchIndex: 0 }),
    );

    expect(cardIds()).toEqual(['b1', 'b2', 'single']);
    expect(screen.getByText('Batch Approval (3 tools)')).toBeInTheDocument();
    const group = screen.getByText('Batch: 2 tools').parentElement as HTMLElement;
    expect(within(group).getAllByTestId('card')).toHaveLength(2);
  });

  it('keeps every batch in a group of its own', () => {
    render(<ToolApprovalDialog />);

    show(
      approvalRequest({ requestId: 'x1', batchId: 'x', batchIndex: 0 }),
      approvalRequest({ requestId: 'y1', batchId: 'y', batchIndex: 0, messageId: 'msg-y' }),
      approvalRequest({ requestId: 'x2', batchId: 'x', batchIndex: 1 }),
    );

    const groups = screen.getAllByText(/^Batch: \d tools$/).map((label) => label.textContent);
    expect(groups).toEqual(['Batch: 2 tools', 'Batch: 1 tools']);
    expect(cardIds()).toEqual(['x1', 'x2', 'y1']);
  });

  it('closes when the last approval is answered', async () => {
    render(<ToolApprovalDialog />);
    show(approvalRequest());

    fireEvent.click(screen.getByRole('button', { name: 'approve req-1' }));

    await vi.waitFor(() => expect(dialog()).toBeNull());
    expect(kit.resume).toHaveBeenCalledTimes(1);
  });

  it('cannot be dismissed by the user, only by answering, and offers no close button that would not work', () => {
    render(<ToolApprovalDialog />);
    show(approvalRequest());

    expect(within(dialog() as HTMLElement).queryByRole('button', { name: 'Close' })).toBeNull();
    fireEvent.keyDown(dialog() as HTMLElement, { key: 'Escape' });
    fireEvent.pointerDown(document.body);

    expect(dialog()).not.toBeNull();
  });

  it('tells its cards, batched or single, and its buttons when an answer is being sent', () => {
    render(<ToolApprovalDialog />);
    show(
      approvalRequest({ requestId: 'b1', batchId: 'batch', batchIndex: 0 }),
      approvalRequest({ requestId: 'b2', batchId: 'batch', batchIndex: 1 }),
      approvalRequest({ requestId: 'single', messageId: 'msg-3' }),
    );
    const loading = () => screen.getAllByTestId('card').map((card) => card.getAttribute('data-loading'));
    expect(loading()).toEqual(['false', 'false', 'false']);

    act(() => useToolApprovalStore.setState({ isResolving: true }));

    expect(loading()).toEqual(['true', 'true', 'true']);
    expect(screen.getByRole('button', { name: 'Approve All' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject All' })).toBeDisabled();
  });
});

describe('ToolApprovalDialog answering several at once', () => {
  it('approves everything it shows, one resume per interrupt', async () => {
    render(<ToolApprovalDialog />);
    show(
      approvalRequest({ requestId: 'a', messageId: 'msg-a' }),
      approvalRequest({ requestId: 'b', messageId: 'msg-b' }),
      approvalRequest({ requestId: 'inline', toolName: 'browser_click' }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Approve All' }));

    await vi.waitFor(() => expect(kit.resume).toHaveBeenCalledTimes(2));
    expect(kit.resume.mock.calls.map(([request]) => (request as ToolApprovalRequest).requestId)).toEqual(['a', 'b']);
    expect(decisions(0)).toEqual([expect.objectContaining({ type: 'approve' })]);
    expect(useToolApprovalStore.getState().queue.map((request) => request.requestId)).toEqual(['inline']);
  });

  it('rejects everything it shows with a reason the agent can read', async () => {
    render(<ToolApprovalDialog />);
    show(
      approvalRequest({ requestId: 'x1', batchId: 'batch', batchIndex: 0 }),
      approvalRequest({ requestId: 'x2', batchId: 'batch', batchIndex: 1 }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reject All' }));

    await vi.waitFor(() => expect(kit.resume).toHaveBeenCalledTimes(1));
    expect(decisions().map((decision) => decision.type)).toEqual(['reject', 'reject']);
    expect(decisions()[0].feedback).toBe('Batch rejected by user');
    await vi.waitFor(() => expect(dialog()).toBeNull());
  });
});
