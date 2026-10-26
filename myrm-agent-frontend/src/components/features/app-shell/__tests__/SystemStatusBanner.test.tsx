import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { apiRequest } from '@/lib/api';
import { confirmAction } from '@/lib/app-dialog';
import { fetchBackendHealth } from '@/lib/backend-health';
import SystemStatusBanner from '../SystemStatusBanner';

type Translator = (key: string, values?: { message?: string }) => string;
const translators = new Map<string, Translator>();
/** One stable translator per namespace, like next-intl's: the banner lists it in an effect's dependencies. */
const translatorFor = (namespace: string): Translator => {
  let translate = translators.get(namespace);
  if (!translate) {
    translate = (key, values) =>
      namespace === 'notifications' && key === 'databaseResetFailedDesc' && values?.message
        ? `error:${values.message}`
        : `${namespace}.${key}`;
    translators.set(namespace, translate);
  }
  return translate;
};

vi.mock('next-intl', () => ({ useTranslations: (namespace: string) => translatorFor(namespace) }));

vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
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
    vi.mocked(fetchBackendHealth).mockReset();
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

  describe('resetting a corrupted database', () => {
    const showBanner = async () => {
      vi.mocked(fetchBackendHealth).mockResolvedValue({
        status: 'healthy',
        system_status: { database_degraded: true },
      });
      render(<SystemStatusBanner />);
      await act(async () => {
        await Promise.resolve();
      });
    };

    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('wipes the local data only after the user confirms the reset', async () => {
      vi.mocked(confirmAction).mockResolvedValue(true);
      vi.mocked(apiRequest).mockResolvedValue(undefined);
      await showBanner();

      fireEvent.click(screen.getByRole('button', { name: 'notifications.databaseResetNow' }));
      await vi.advanceTimersByTimeAsync(0);

      expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
        variant: 'destructive',
        description: 'notifications.databaseResetConfirm',
        confirmText: 'notifications.databaseResetNow',
      });
      expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/health/database/reset', { method: 'POST', silent: true });
      expect(toast.success).toHaveBeenCalledWith('notifications.databaseResetSuccessTitle', expect.anything());
    });

    it('touches nothing when the user declines', async () => {
      vi.mocked(confirmAction).mockResolvedValue(false);
      await showBanner();

      fireEvent.click(screen.getByRole('button', { name: 'notifications.databaseResetNow' }));
      await vi.advanceTimersByTimeAsync(0);

      expect(confirmAction).toHaveBeenCalledTimes(1);
      expect(apiRequest).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'notifications.databaseResetNow' })).toBeEnabled();
    });
  });

  describe('vector store degradation', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it('shows a persistent dismissible warning toast when vector_degraded is true', async () => {
      vi.mocked(fetchBackendHealth).mockResolvedValue({
        status: 'healthy',
        system_status: { vector_degraded: true },
      });

      render(<SystemStatusBanner />);

      await act(async () => {
        await Promise.resolve();
      });

      expect(toast.warning).toHaveBeenCalledTimes(1);
      expect(toast.warning).toHaveBeenCalledWith(
        'notifications.vectorDegradedTitle',
        expect.objectContaining({
          id: 'vector-degraded',
          description: 'notifications.vectorDegradedDesc',
          duration: Number.POSITIVE_INFINITY,
          dismissible: true,
        }),
      );
      expect(screen.queryByText('notifications.databaseDegradedTitle')).not.toBeInTheDocument();
    });

    it('stays silent when the vector store is persistent', async () => {
      vi.mocked(fetchBackendHealth).mockResolvedValue({
        status: 'healthy',
        system_status: { vector_degraded: false },
      });

      render(<SystemStatusBanner />);

      await act(async () => {
        await Promise.resolve();
      });

      expect(toast.warning).not.toHaveBeenCalled();
    });

    it('catches a degradation reported after the first read and stops rechecking', async () => {
      vi.useFakeTimers();
      vi.mocked(fetchBackendHealth)
        .mockResolvedValueOnce({ status: 'healthy', system_status: { vector_degraded: false } })
        .mockResolvedValue({ status: 'healthy', system_status: { vector_degraded: true } });

      render(<SystemStatusBanner />);
      await vi.advanceTimersByTimeAsync(0);
      expect(toast.warning).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(8_000);
      expect(toast.warning).toHaveBeenCalledTimes(1);

      await vi.advanceTimersByTimeAsync(120_000);
      expect(toast.warning).toHaveBeenCalledTimes(1);
      expect(fetchBackendHealth).toHaveBeenCalledTimes(2);
    });

    it('limits rechecks to three and stops them on unmount', async () => {
      vi.useFakeTimers();
      vi.mocked(fetchBackendHealth).mockResolvedValue({
        status: 'healthy',
        system_status: { vector_degraded: false },
      });

      const { unmount } = render(<SystemStatusBanner />);
      await vi.advanceTimersByTimeAsync(120_000);
      expect(fetchBackendHealth).toHaveBeenCalledTimes(4);

      unmount();
      await vi.advanceTimersByTimeAsync(120_000);
      expect(fetchBackendHealth).toHaveBeenCalledTimes(4);
    });

    it('cancels pending rechecks when unmounted before they fire', async () => {
      vi.useFakeTimers();
      vi.mocked(fetchBackendHealth).mockResolvedValue({
        status: 'healthy',
        system_status: { vector_degraded: true },
      });

      const { unmount } = render(<SystemStatusBanner />);
      unmount();
      await vi.advanceTimersByTimeAsync(120_000);

      expect(toast.warning).not.toHaveBeenCalled();
      expect(fetchBackendHealth).toHaveBeenCalledTimes(1);
    });
  });
});
