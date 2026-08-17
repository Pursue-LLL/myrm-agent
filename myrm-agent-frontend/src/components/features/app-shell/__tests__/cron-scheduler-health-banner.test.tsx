import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CronSchedulerHealthBanner, {
  dismissCronSchedulerBanner,
  isCronSchedulerBannerDismissed,
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

const mockSubscribe = vi.fn();

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
    mockSubscribe(listener);
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

describe('isCronSchedulerBannerDismissed', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns false when sessionStorage has no dismiss key', () => {
    expect(isCronSchedulerBannerDismissed()).toBe(false);
  });

  it('returns true after dismissCronSchedulerBanner', () => {
    dismissCronSchedulerBanner();
    expect(isCronSchedulerBannerDismissed()).toBe(true);
  });
});

describe('CronSchedulerHealthBanner', () => {
  beforeEach(async () => {
    sessionStorage.clear();
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
    dismissCronSchedulerBanner();

    render(<CronSchedulerHealthBanner />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByTestId('cron-scheduler-health-banner')).not.toBeInTheDocument();
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
    expect(isCronSchedulerBannerDismissed()).toBe(true);
  });
});
