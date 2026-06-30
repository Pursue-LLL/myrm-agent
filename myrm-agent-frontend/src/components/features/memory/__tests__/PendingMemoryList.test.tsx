import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PendingMemoryList from '../PendingMemoryList';

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  dismiss: vi.fn(),
}));

const mockBatchApprove = vi.hoisted(() => vi.fn());
const mockBatchReject = vi.hoisted(() => vi.fn());
const mockSelectAllPending = vi.hoisted(() => vi.fn());
const mockToggleSelectPending = vi.hoisted(() => vi.fn());
const mockFetchPendingMemories = vi.hoisted(() => vi.fn());
const mockFetchConflicts = vi.hoisted(() => vi.fn());
const mockApproveMemory = vi.hoisted(() => vi.fn());
const mockRejectMemory = vi.hoisted(() => vi.fn());
const mockResolveConflict = vi.hoisted(() => vi.fn());

const selectedPendingIds = new Set(['mem-1', 'mem-2']);

vi.mock('@/hooks/useToast', () => ({
  toast: toastMock,
}));

vi.mock('@/store/memory', () => ({
  useMemoryStore: () => ({
    pendingMemories: [
      { id: 'mem-1', content: 'Memory 1', type: 'fact', source: 'conversation', created_at: '2024-01-01' },
      { id: 'mem-2', content: 'Memory 2', type: 'preference', source: 'conversation', created_at: '2024-01-02' },
    ],
    pendingLoading: false,
    pendingError: null,
    selectedPendingIds,
    toggleSelectPending: mockToggleSelectPending,
    selectAllPending: mockSelectAllPending,
    batchApprove: mockBatchApprove,
    batchReject: mockBatchReject,
    approveMemory: mockApproveMemory,
    rejectMemory: mockRejectMemory,
    fetchPendingMemories: mockFetchPendingMemories,
    conflicts: [],
    conflictsLoading: false,
    fetchConflicts: mockFetchConflicts,
    resolveConflict: mockResolveConflict,
  }),
}));

vi.mock('../MemoryCard', () => ({
  default: ({ memory, onApprove, onReject }: { memory: { id: string; content: string }; onApprove: () => void; onReject: () => void }) => (
    <div data-testid={`memory-card-${memory.id}`}>
      <span>{memory.content}</span>
      <button onClick={onApprove}>approve-{memory.id}</button>
      <button onClick={onReject}>reject-{memory.id}</button>
    </div>
  ),
}));

vi.mock('../ConflictCard', () => ({
  default: () => <div data-testid="conflict-card" />,
}));

describe('PendingMemoryList - batch operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders batch action buttons when items are selected', () => {
    render(<PendingMemoryList />);
    expect(screen.getByText('batchReject')).toBeInTheDocument();
    expect(screen.getByText('batchAccept')).toBeInTheDocument();
  });

  it('calls batchApprove and shows success toast', async () => {
    mockBatchApprove.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<PendingMemoryList />);

    await user.click(screen.getByText('batchAccept'));

    await waitFor(() => {
      expect(mockBatchApprove).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'batchApproveSuccess',
        description: 'batchApproveSuccessDesc',
      });
    });
  });

  it('calls batchReject and shows success toast', async () => {
    mockBatchReject.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<PendingMemoryList />);

    await user.click(screen.getByText('batchReject'));

    await waitFor(() => {
      expect(mockBatchReject).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'batchRejectSuccess',
        description: 'batchRejectSuccessDesc',
      });
    });
  });

  it('shows error toast when batchApprove fails', async () => {
    mockBatchApprove.mockRejectedValueOnce(new Error('Approve failed'));
    const user = userEvent.setup();
    render(<PendingMemoryList />);

    await user.click(screen.getByText('batchAccept'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'batchApproveFailed',
        description: 'Approve failed',
        variant: 'destructive',
      });
    });
  });

  it('shows error toast when batchReject fails', async () => {
    mockBatchReject.mockRejectedValueOnce(new Error('Reject failed'));
    const user = userEvent.setup();
    render(<PendingMemoryList />);

    await user.click(screen.getByText('batchReject'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'batchRejectFailed',
        description: 'Reject failed',
        variant: 'destructive',
      });
    });
  });

  it('disables buttons during batch approve processing', async () => {
    let resolveApprove: () => void;
    mockBatchApprove.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveApprove = resolve;
      }),
    );

    const user = userEvent.setup();
    render(<PendingMemoryList />);

    const approveButton = screen.getByText('batchAccept').closest('button')!;
    const rejectButton = screen.getByText('batchReject').closest('button')!;

    await user.click(approveButton);

    await waitFor(() => {
      expect(approveButton).toBeDisabled();
      expect(rejectButton).toBeDisabled();
    });

    resolveApprove!();

    await waitFor(() => {
      expect(approveButton).not.toBeDisabled();
      expect(rejectButton).not.toBeDisabled();
    });
  });

  it('prevents concurrent batch operations (approve blocks reject)', async () => {
    let resolveApprove: () => void;
    mockBatchApprove.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveApprove = resolve;
      }),
    );

    const user = userEvent.setup();
    render(<PendingMemoryList />);

    await user.click(screen.getByText('batchAccept'));

    await waitFor(() => {
      expect(mockBatchApprove).toHaveBeenCalledTimes(1);
    });

    expect(mockBatchReject).not.toHaveBeenCalled();

    resolveApprove!();

    await waitFor(() => {
      expect(mockBatchApprove).toHaveBeenCalledTimes(1);
    });
  });
});
