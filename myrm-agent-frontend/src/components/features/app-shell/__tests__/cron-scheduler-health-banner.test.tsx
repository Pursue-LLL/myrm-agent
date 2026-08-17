import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CronSchedulerHealthBanner, {
  dismissCronSchedulerBanner,
  getCronSchedulerBannerDismissedStatus,
} from '../cron-scheduler-health-banner';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => {
    const t = (key: string): string => {
      if (namespace === 'common') {
        return key === 'close' ? 'close' : key;
      }
      if (namespace === 'cron.schedulerBanner') {
        const labels: Record<string, string> = {
          degradedTitle: 'Scheduled tasks may be delayed',
          degradedDescription: 'Degraded description',
          stoppedTitle: 'Scheduled tasks are not running',
          stoppedDescription: 'Stopped description',
          viewCron: 'View scheduled tasks',
        };
        return labels[key] ?? key;
      }
      return key;
    };
    return t;
  },
}));

const subscribeMock = vi.fn();

vi.mock('@/lib/cron/schedulerHealth', () => ({
  subscribeSchedulerHealth: (
    listener: (health: {
      status: 'green' | 'yellow' | 'red';
      running: boolean;
      last_tick_at: string | null;
      tick_errors: number;
      last_tick_age_seconds: number | null;
      has_timer: boolean;
    } | null) => void,
  ) => {
    subscribeMock(listener);
    listener({
      status: 'red',
      running: false,
      last_tick_at: null,
      tick_errors: 0,
      last_tick_age_seconds: null,
      has_timer: false,
    });
    return () => undefined;
  },
}));

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/chat'),
}));

describe('getCronSchedulerBannerDismissedStatus', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns null when sessionStorage has no dismiss key', () => {
    expect(getCronSchedulerBannerDismissedStatus()).toBeNull();
  });

  it('returns stored status after dismissCronSchedulerBanner', () => {
    dismissCronSchedulerBanner('yellow');
    expect(getCronSchedulerBannerDismissedStatus()).toBe('yellow');
  });
});

describe('CronSchedulerHealthBanner', () => {
  beforeEach(async () => {
    sessionStorage.clear();
    subscribeMock.mockClear();
    const { usePathname } = await import('next/navigation');
    vi.mocked(usePathname).mockReturnValue('/chat');
  });

  it('shows banner when scheduler health is red', async () => {
    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('cron-scheduler-health-banner')).toBeInTheDocument();
    expect(screen.getByText('Scheduled tasks are not running')).toBeInTheDocument();
  });

  it('hides banner when dismissed for the session', async () => {
    dismissCronSchedulerBanner('red');

    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('cron-scheduler-health-banner')).not.toBeInTheDocument();
  });

  it('re-shows banner when status worsens from dismissed yellow to red', async () => {
    dismissCronSchedulerBanner('yellow');

    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId('cron-scheduler-health-banner')).toBeInTheDocument();
  });

  it('hides banner on cron settings page', async () => {
    const { usePathname } = await import('next/navigation');
    vi.mocked(usePathname).mockReturnValue('/settings/cron');

    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('cron-scheduler-health-banner')).not.toBeInTheDocument();
  });

  it('dismisses banner on close click', async () => {
    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    expect(screen.queryByTestId('cron-scheduler-health-banner')).not.toBeInTheDocument();
    expect(getCronSchedulerBannerDismissedStatus()).toBe('red');
  });
});
