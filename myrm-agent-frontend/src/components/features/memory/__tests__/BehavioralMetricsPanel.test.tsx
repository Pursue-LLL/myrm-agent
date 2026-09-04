/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BehavioralMetricsPanel } from '../insights/BehavioralMetricsPanel';
import * as commandCenterService from '@/services/memory/commandCenter';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values) {
    return Object.entries(values).reduce(
      (acc, [k, v]) => acc.replace(`{${k}}`, String(v)),
      key
    );
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

describe('BehavioralMetricsPanel Component', () => {
  const mockInsights: commandCenterService.MemoryBehavioralInsights = {
    hour_histogram: Array.from({ length: 24 }, (_, i) => (i === 14 ? 10 : 1)),
    workday_hour_histogram: Array.from({ length: 24 }, (_, i) => (i === 14 ? 8 : 0)),
    weekend_hour_histogram: Array.from({ length: 24 }, (_, i) => (i === 20 ? 5 : 0)),
    weekday_histogram: [5, 5, 5, 5, 5, 2, 2],
    reply_latency_p50_ms: 12500,
    reply_latency_p90_ms: 25000,
    self_message_count: 29,
    latency_sample_count: 15,
    channel_distribution: { webui: 20, slack: 9 },
    peak_active_window: '14:00 - 18:00',
    workday_peak_window: '14:00 - 18:00',
    weekend_peak_window: '20:00 - 24:00',
    top_collaborators: [
      ['Alice', 14],
      ['Bob', 8],
    ],
    offset_minutes: 480,
    source: 'computed_deterministic',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders insights correctly after data is fetched', async () => {
    vi.spyOn(commandCenterService, 'getBehavioralInsights').mockResolvedValue(mockInsights);

    render(<BehavioralMetricsPanel />);

    // Expect loading state first or title
    expect(screen.getByText('title')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('14:00 - 18:00')).toBeInTheDocument();
      expect(screen.getByText('12.5s')).toBeInTheDocument();
      expect(screen.getAllByText('Alice')[0]).toBeInTheDocument();
      expect(screen.getByText('Bob')).toBeInTheDocument();
    });
  });

  it('switches between workday, weekend and combined tabs', async () => {
    const user = userEvent.setup();
    vi.spyOn(commandCenterService, 'getBehavioralInsights').mockResolvedValue(mockInsights);

    render(<BehavioralMetricsPanel />);

    await waitFor(() => {
      expect(screen.getByText('14:00 - 18:00')).toBeInTheDocument();
    });

    const weekendButton = screen.getByText('weekend');
    await user.click(weekendButton);

    const allDaysButton = screen.getByText('allDays');
    await user.click(allDaysButton);
  });

  it('triggers profile synchronization and shows success toast', async () => {
    const user = userEvent.setup();
    vi.spyOn(commandCenterService, 'getBehavioralInsights').mockResolvedValue(mockInsights);
    const syncSpy = vi.spyOn(commandCenterService, 'triggerBehavioralSync').mockResolvedValue({
      status: 'success',
      updated_profile_keys: ['routine_active_hours', 'routine_reply_latency'],
      count: 2,
    });

    render(<BehavioralMetricsPanel />);

    await waitFor(() => {
      expect(screen.getByText('syncProfile')).toBeInTheDocument();
    });

    const syncBtn = screen.getByRole('button', { name: /syncProfile/i });
    await user.click(syncBtn);

    expect(syncSpy).toHaveBeenCalledTimes(1);
  });
});
