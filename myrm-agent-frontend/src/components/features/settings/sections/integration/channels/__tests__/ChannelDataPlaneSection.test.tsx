/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockGetStats = vi.fn();
const mockClearChannel = vi.fn();

vi.mock('@/services/channels', () => ({
  getChannelDataPlaneStats: (...args: unknown[]) => mockGetStats(...args),
  clearChannelDataPlane: (...args: unknown[]) => mockClearChannel(...args),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => {
  const toastFn = vi.fn();
  (toastFn as unknown as Record<string, unknown>).success = vi.fn();
  (toastFn as unknown as Record<string, unknown>).error = vi.fn();
  (toastFn as unknown as Record<string, unknown>).warning = vi.fn();
  (toastFn as unknown as Record<string, unknown>).info = vi.fn();
  (toastFn as unknown as Record<string, unknown>).promise = vi.fn();
  (toastFn as unknown as Record<string, unknown>).loading = vi.fn();
  (toastFn as unknown as Record<string, unknown>).dismiss = vi.fn();
  (toastFn as unknown as Record<string, unknown>).message = vi.fn();
  return { toast: toastFn };
});

import { ChannelDataPlaneSection } from '../ChannelDataPlaneSection';

describe('ChannelDataPlaneSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStats.mockResolvedValue({
      total_messages: 120,
      ambient_messages: 95,
      trigger_messages: 25,
      learning_eligible: 78,
    });
    mockClearChannel.mockResolvedValue({ deleted_count: 120 });
  });

  it('renders title and loads statistics on mount', async () => {
    render(<ChannelDataPlaneSection channel="wechat" />);

    expect(screen.getByText('title')).toBeTruthy();
    expect(screen.getByText('description')).toBeTruthy();

    await waitFor(() => {
      expect(mockGetStats).toHaveBeenCalledWith('wechat');
      expect(screen.getByText('120')).toBeTruthy();
      expect(screen.getByText('95')).toBeTruthy();
      expect(screen.getByText('25')).toBeTruthy();
      expect(screen.getByText('78')).toBeTruthy();
    });
  });

  it('handles two-step confirmation for clear history action', async () => {
    render(<ChannelDataPlaneSection channel="slack" />);

    await waitFor(() => {
      expect(screen.getByText('120')).toBeTruthy();
    });

    const clearBtn = screen.getByText('clearHistory');
    fireEvent.click(clearBtn);

    // Enters confirming state
    expect(screen.getByText('clearConfirm')).toBeTruthy();

    // Confirm click
    fireEvent.click(screen.getByText('clearConfirm'));

    await waitFor(() => {
      expect(mockClearChannel).toHaveBeenCalledWith('slack');
      expect(mockGetStats).toHaveBeenCalledTimes(2);
    });
  });

  it('supports manual refresh button', async () => {
    render(<ChannelDataPlaneSection channel="slack" />);

    await waitFor(() => {
      expect(screen.getByText('120')).toBeTruthy();
    });

    const refreshBtn = screen.getByText('refresh');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetStats).toHaveBeenCalledTimes(2);
    });
  });
});
