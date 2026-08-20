/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetMemories = vi.fn();
const mockCreateMemory = vi.fn();
const mockDeleteMemory = vi.fn();
const mockToastError = vi.fn();
const mockToastSuccess = vi.fn();

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
    success: (...args: unknown[]) => mockToastSuccess(...args),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
  },
}));

vi.mock('@/services/memory', () => ({
  getMemories: (...args: unknown[]) => mockGetMemories(...args),
  createMemory: (...args: unknown[]) => mockCreateMemory(...args),
  deleteMemory: (...args: unknown[]) => mockDeleteMemory(...args),
}));

import BrandStudioSection from '../BrandStudioSection';

const baseResponse = {
  items: [
    {
      id: 'm1',
      memory_type: 'profile',
      content: 'brand_name: Acme Studio',
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      key: 'brand_name',
      value: 'Acme Studio',
    },
  ],
  pagination: { page: 1, page_size: 100, total: 1, total_pages: 1, has_next: false, has_prev: false },
};

describe('BrandStudioSection reset confirmation', () => {
  beforeEach(() => {
    mockGetMemories.mockReset();
    mockCreateMemory.mockReset();
    mockDeleteMemory.mockReset();
    mockToastError.mockClear();
    mockToastSuccess.mockClear();
    mockGetMemories.mockResolvedValue(baseResponse);
  });

  it('keeps the brand value when the destructive dialog is cancelled', async () => {
    const user = userEvent.setup();
    render(<BrandStudioSection />);

    // Wait for the seeded brand memory to render.
    await waitFor(() => {
      expect(mockGetMemories).toHaveBeenCalledTimes(1);
    });

    // The Clear trigger (destructive) opens the confirm dialog.
    await user.click(screen.getByRole('button', { name: /reset/i }));

    // The dialog exposes a cancel action with a dedicated testid.
    const cancelButton = screen.getByTestId('confirm-dialog-cancel');
    await user.click(cancelButton);

    // The value must be preserved (no reset happened).
    expect(screen.getByPlaceholderText(/placeholders\.name/i)).toHaveValue('Acme Studio');
    // The dialog is now closed.
    expect(screen.queryByTestId('confirm-dialog-confirm')).not.toBeInTheDocument();
  });

  it('empties the form after confirming, then save issues the profile delete', async () => {
    const user = userEvent.setup();
    render(<BrandStudioSection />);

    await waitFor(() => {
      expect(mockGetMemories).toHaveBeenCalledTimes(1);
    });

    // Open the dialog, then confirm the destructive action.
    await user.click(screen.getByRole('button', { name: /reset/i }));
    await user.click(screen.getByTestId('confirm-dialog-confirm'));

    // The form name field is emptied.
    expect(screen.getByPlaceholderText(/placeholders\.name/i)).toHaveValue('');

    // Saving an emptied form deletes the previously configured brand memory.
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(mockDeleteMemory).toHaveBeenCalledWith('brand_name', 'profile');
    });
  });

  it('disables the clear trigger when the form has no brand value', async () => {
    mockGetMemories.mockResolvedValue({ ...baseResponse, items: [] });
    const user = userEvent.setup();
    render(<BrandStudioSection />);

    await waitFor(() => {
      expect(mockGetMemories).toHaveBeenCalledTimes(1);
    });

    const clearButton = screen.getByRole('button', { name: /reset/i });
    expect(clearButton).toBeDisabled();
    // No dialog can be opened from a disabled trigger.
    await user.click(clearButton);
    expect(screen.queryByTestId('confirm-dialog-confirm')).not.toBeInTheDocument();
  });
});
