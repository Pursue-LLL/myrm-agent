/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SchedulerHealthBadge from '../SchedulerHealthBadge';

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'ja-JP',
}));

vi.mock('@/lib/cron/schedulerHealth', () => ({
  getCachedSchedulerHealth: () => ({
    status: 'green',
    running: true,
    last_tick_at: '2026-06-17T08:30:00.000Z',
    tick_errors: 0,
    last_tick_age_seconds: 1,
    has_timer: true,
  }),
  subscribeSchedulerHealth: () => () => undefined,
}));

describe('SchedulerHealthBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('formats last_tick tooltip with locale-aware formatTime', () => {
    render(<SchedulerHealthBadge />);

    expect(screen.getByText(/schedulerStatus\.lastTick/)).toBeInTheDocument();
    expect(screen.getByText(/2026\/06\/17 16:30/)).toBeInTheDocument();
  });
});
