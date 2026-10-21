/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';
import { TooltipProvider } from '@/components/primitives/tooltip';
import PendingMemoryDialog from '../PendingMemoryDialog';
import { ApiError } from '@/lib/api';
import type { PendingMemory } from '@/services/memory/core';

const { mockApproveMemory, mockRejectMemory, mockCloseConfirmDialog, mockState, toastMock } = vi.hoisted(() => {
  const toastFn = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() });
  return {
    mockApproveMemory: vi.fn().mockResolvedValue(undefined),
    mockRejectMemory: vi.fn().mockResolvedValue(undefined),
    mockCloseConfirmDialog: vi.fn(),
    mockState: {
      currentPendingMemory: null as PendingMemory | null,
      isConfirmDialogOpen: true,
    },
    toastMock: toastFn,
  };
});

const stablePendingMemoryTranslations: Record<string, string> = {
  confirmTitle: 'Confirm Memory',
  confirmDescription: 'Do you want to store this memory?',
  confidenceHigh: 'High',
  confidenceMedium: 'Medium',
  confidenceLow: 'Low',
  extractionReason: 'Extraction Reasoning',
  validPermanent: 'Permanent',
  approve: 'Approve',
  reject: 'Reject',
  accept: 'Accept',
  edit: 'Edit',
  cancel: 'Cancel',
  'types.semantic': 'Semantic Memory',
};
const stableT = (key: string) => stablePendingMemoryTranslations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('@/store/memory', () => ({
  useMemoryStore: () => ({
    currentPendingMemory: mockState.currentPendingMemory,
    isConfirmDialogOpen: mockState.isConfirmDialogOpen,
    closeConfirmDialog: mockCloseConfirmDialog,
    approveMemory: mockApproveMemory,
    rejectMemory: mockRejectMemory,
  }),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

vi.mock('../cards/MemoryTypeIcon', () => ({
  default: () => <div data-testid="memory-type-icon" />,
}));

const renderWithProviders = (ui: React.ReactElement) => {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
};

describe('PendingMemoryDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApproveMemory.mockResolvedValue(undefined);
    mockRejectMemory.mockResolvedValue(undefined);
    mockState.isConfirmDialogOpen = true;
    mockState.currentPendingMemory = {
      id: 'pending-1',
      user_id: 'user-1',
      memory_type: 'semantic',
      content: 'User prefers dark mode and TypeScript.',
      status: 'pending',
      created_at: '2026-08-27T10:00:00Z',
      confidence: 0.92,
      importance: 0.85,
      kind: 'preference',
      influence_explanation: 'Extracted because user said they love dark mode.',
      expected_valid_days: 30,
      tags: ['theme', 'ts'],
    };
  });

  it('renders structured metadata badges including high confidence, kind, validity, and reasoning', () => {
    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.getByText(/92% High/)).toBeInTheDocument();
    expect(screen.getByText('preference')).toBeInTheDocument();
    expect(screen.getByText('30d')).toBeInTheDocument();
    expect(screen.getByText('User prefers dark mode and TypeScript.')).toBeInTheDocument();
    expect(screen.getByText('Extracted because user said they love dark mode.')).toBeInTheDocument();
  });

  it('renders permanent validity fallback when expected_valid_days is missing', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = {
      ...mockState.currentPendingMemory,
      expected_valid_days: undefined,
      confidence: 0.72,
    };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.getByText(/72% Medium/)).toBeInTheDocument();
    expect(screen.getByText('Permanent')).toBeInTheDocument();
  });

  it('calls approveMemory on approve button click', async () => {
    renderWithProviders(<PendingMemoryDialog />);

    const approveButton = screen.getByRole('button', { name: /Accept/i });
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(mockApproveMemory).toHaveBeenCalledWith('pending-1', undefined);
    });
  });

  it('tells the user a suggestion is out of date instead of showing backend text', async () => {
    mockApproveMemory.mockRejectedValue(new ApiError('Memory mem-1 is no longer what proposal pending-1 was queued against (content_changed); review it again', 409));
    renderWithProviders(<PendingMemoryDialog />);

    fireEvent.click(screen.getByRole('button', { name: /Accept/i }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith({
        title: 'targetChangedTitle',
        description: 'targetChangedDesc',
        variant: 'default',
      });
    });
  });

  it('calls rejectMemory on reject button click', async () => {
    renderWithProviders(<PendingMemoryDialog />);

    const rejectButton = screen.getByRole('button', { name: /Reject/i });
    fireEvent.click(rejectButton);

    await waitFor(() => {
      expect(mockRejectMemory).toHaveBeenCalledWith('pending-1');
    });
  });

  it('discloses the correction target when approving a CORRECT proposal', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = {
      ...mockState.currentPendingMemory,
      resolution_action: 'correct',
      target_memory_id: 'mem-old',
      target_content: 'User preferred light mode.',
    };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.getByTestId('pending-target-hint')).toBeInTheDocument();
    expect(screen.getByText('fields.willCorrect')).toBeInTheDocument();
    expect(screen.getByText('User preferred light mode.', { exact: false })).toBeInTheDocument();
  });

  it('warns before a delete proposal removes an existing memory', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = {
      ...mockState.currentPendingMemory,
      resolution_action: 'delete',
      target_memory_id: 'mem-old',
      target_content: 'User lived in Berlin.',
    };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.getByTestId('pending-target-hint')).toBeInTheDocument();
    expect(screen.getByText('fields.willDelete')).toBeInTheDocument();
  });

  it('lets the reviewer reword a plain addition and sends the edit with approval', async () => {
    renderWithProviders(<PendingMemoryDialog />);

    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.change(screen.getByPlaceholderText('editPlaceholder'), { target: { value: 'Reworded memory.' } });
    fireEvent.click(screen.getByRole('button', { name: /saveAndAccept/i }));

    await waitFor(() => {
      expect(mockApproveMemory).toHaveBeenCalledWith('pending-1', 'Reworded memory.');
    });
  });

  it('keeps the reviewer edit when approval fails so it can be retried', async () => {
    mockApproveMemory.mockRejectedValueOnce(new ApiError('Network down', 500));
    renderWithProviders(<PendingMemoryDialog />);

    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.change(screen.getByPlaceholderText('editPlaceholder'), { target: { value: 'Reworded memory.' } });
    fireEvent.click(screen.getByRole('button', { name: /saveAndAccept/i }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalled();
    });
    expect(screen.getByPlaceholderText('editPlaceholder')).toHaveValue('Reworded memory.');

    fireEvent.click(screen.getByRole('button', { name: /saveAndAccept/i }));
    await waitFor(() => {
      expect(mockApproveMemory).toHaveBeenLastCalledWith('pending-1', 'Reworded memory.');
    });
    expect(mockApproveMemory).toHaveBeenCalledTimes(2);
  });

  it('leaves edit mode once an edited approval succeeds', async () => {
    renderWithProviders(<PendingMemoryDialog />);

    fireEvent.click(screen.getByRole('button', { name: /Edit/i }));
    fireEvent.change(screen.getByPlaceholderText('editPlaceholder'), { target: { value: 'Reworded memory.' } });
    fireEvent.click(screen.getByRole('button', { name: /saveAndAccept/i }));

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('editPlaceholder')).not.toBeInTheDocument();
    });
  });

  it('offers no edit for forget proposals, which carry no text to reword', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = {
      ...mockState.currentPendingMemory,
      resolution_action: 'delete',
      target_memory_id: 'mem-old',
    };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument();
  });

  it('offers no edit for profile entries', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = { ...mockState.currentPendingMemory, memory_type: 'profile' };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.queryByRole('button', { name: /Edit/i })).not.toBeInTheDocument();
  });

  it('shows no target hint for plain additions', () => {
    expectNonNull(mockState.currentPendingMemory, 'mockState.currentPendingMemory');
    mockState.currentPendingMemory = { ...mockState.currentPendingMemory, resolution_action: 'store' };

    renderWithProviders(<PendingMemoryDialog />);

    expect(screen.queryByTestId('pending-target-hint')).not.toBeInTheDocument();
  });
});
