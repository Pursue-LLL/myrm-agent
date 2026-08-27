/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '@/components/primitives/tooltip';
import PendingMemoryDialog from '../PendingMemoryDialog';
import type { PendingMemory } from '@/services/memory/core';

const { mockApproveMemory, mockRejectMemory, mockCloseConfirmDialog, mockState, toastMock } = vi.hoisted(() => {
  const toastFn = vi.fn();
  (toastFn as any).success = vi.fn();
  (toastFn as any).error = vi.fn();
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

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const translations: Record<string, string> = {
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
    return translations[key] || key;
  },
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
    mockState.currentPendingMemory = {
      ...mockState.currentPendingMemory!,
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

  it('calls rejectMemory on reject button click', async () => {
    renderWithProviders(<PendingMemoryDialog />);

    const rejectButton = screen.getByRole('button', { name: /Reject/i });
    fireEvent.click(rejectButton);

    await waitFor(() => {
      expect(mockRejectMemory).toHaveBeenCalledWith('pending-1');
    });
  });
});
