import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SystemStatusBanner from '../SystemStatusBanner';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: { message?: string }) => {
    if (namespace === 'notifications' && key === 'databaseResetFailedDesc' && values?.message) {
      return `error:${values.message}`;
    }
    if (namespace === 'common' && key === 'close') {
      return 'common.close';
    }
    return `${namespace}.${key}`;
  },
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

vi.mock('@/lib/backend-health', () => ({
  fetchBackendHealth: vi.fn(),
}));

describe('SystemStatusBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('shows degraded banner with i18n copy when database_degraded is true', async () => {
    const { fetchBackendHealth } = await import('@/lib/backend-health');
    vi.mocked(fetchBackendHealth).mockResolvedValueOnce({
      status: 'healthy',
      system_status: { database_degraded: true },
    });

    render(<SystemStatusBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('notifications.databaseDegradedTitle')).toBeInTheDocument();
    expect(screen.getByText('notifications.databaseDegradedBody')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'notifications.databaseResetNow' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.close' })).toBeInTheDocument();
  });

  it('does not show banner when database is healthy', async () => {
    const { fetchBackendHealth } = await import('@/lib/backend-health');
    vi.mocked(fetchBackendHealth).mockResolvedValueOnce({
      status: 'healthy',
      system_status: { database_degraded: false },
    });

    render(<SystemStatusBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByText('notifications.databaseDegradedTitle')).not.toBeInTheDocument();
  });

  it('shows recovered toast with i18n when database_recovered is true', async () => {
    const { toast } = await import('sonner');
    const { fetchBackendHealth } = await import('@/lib/backend-health');
    vi.mocked(fetchBackendHealth).mockResolvedValueOnce({
      status: 'healthy',
      system_status: { database_recovered: true, database_degraded: false },
    });

    render(<SystemStatusBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(toast.success).toHaveBeenCalledWith(
      'notifications.databaseRecoveredTitle',
      expect.objectContaining({
        description: 'notifications.databaseRecoveredDesc',
      }),
    );
    expect(screen.queryByText('notifications.databaseDegradedTitle')).not.toBeInTheDocument();
  });

  it('hides banner after dismiss', async () => {
    const { fetchBackendHealth } = await import('@/lib/backend-health');
    vi.mocked(fetchBackendHealth).mockResolvedValueOnce({
      status: 'healthy',
      system_status: { database_degraded: true },
    });

    render(<SystemStatusBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole('button', { name: 'common.close' }));
    expect(screen.queryByText('notifications.databaseDegradedTitle')).not.toBeInTheDocument();
  });
});
