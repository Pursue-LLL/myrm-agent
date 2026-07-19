/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const mockGetMemoryGuardianOverview = vi.fn();
const mockTriggerMemoryMaintenance = vi.fn();
const mockUpdateMemoryGuardianPolicy = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/services/memory', () => ({
  getMemoryGuardianOverview: (...args: unknown[]) => mockGetMemoryGuardianOverview(...args),
  triggerMemoryMaintenance: (...args: unknown[]) => mockTriggerMemoryMaintenance(...args),
  updateMemoryGuardianPolicy: (...args: unknown[]) => mockUpdateMemoryGuardianPolicy(...args),
}));

vi.mock('../MemoryGuardianDigestPanel', () => ({
  default: () => <div data-testid="memory-guardian-digest-panel" />,
}));

vi.mock('../MemoryGuardianPolicyPanel', () => ({
  default: () => <div data-testid="memory-guardian-policy-panel" />,
}));

import MemoryGuardianCard from '../MemoryGuardianCard';

const baseOverview = {
  health: {
    total: 84,
    dimensions: {
      freshness: 90,
    },
    suggestions: [],
    has_graph: false,
  },
  guardian: {
    running: true,
    last_run: null,
    next_run: null,
    healthy_interval_hours: 6,
    unhealthy_interval_hours: 2,
    health_threshold: 70,
    seconds_until_next: null,
    frequency_tier: 'balanced',
    quiet_window_enabled: false,
    quiet_window_start_hour: 0,
    quiet_window_end_hour: 6,
    timezone_offset_minutes: 0,
    local_hour: 10,
    within_quiet_window: false,
    seconds_until_quiet_window: 0,
  },
  policy: {
    frequency_tier: 'balanced',
    quiet_window_enabled: false,
    quiet_window_start_hour: 0,
    quiet_window_end_hour: 6,
    timezone_offset_minutes: 0,
  },
  digest: {
    available: false,
  },
};

describe('MemoryGuardianCard', () => {
  beforeEach(() => {
    mockGetMemoryGuardianOverview.mockReset();
    mockTriggerMemoryMaintenance.mockReset();
    mockUpdateMemoryGuardianPolicy.mockReset();
  });

  it('renders escalated guard alert with observed and threshold details', async () => {
    mockGetMemoryGuardianOverview.mockResolvedValue({
      ...baseOverview,
      alerts: {
        guard_unavailable: {
          active: true,
          escalated: true,
          window_hours: 24,
          total: 4,
          reasons: {
            budget_guard_unavailable: 3,
            capacity_guard_unavailable: 1,
          },
          dominant_reason: 'budget_guard_unavailable',
          dominant_reason_count: 3,
          dominant_reason_ratio: 0.75,
          thresholds: {
            min_total_events: 2,
            escalation_min_reason_count: 2,
            escalation_min_reason_ratio: 0.6,
          },
          last_occurred_at: '2026-07-18T00:00:00+00:00',
        },
      },
    });

    render(<MemoryGuardianCard />);

    await waitFor(() => {
      expect(mockGetMemoryGuardianOverview).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/guardAlertObservedDetail/)).toBeInTheDocument();
    expect(screen.getByText(/guardAlertThresholdDetail/)).toBeInTheDocument();
    expect(screen.getByText('guardAlertEscalatedHint')).toBeInTheDocument();
  });

  it('renders monitoring alert when thresholds are absent in payload', async () => {
    mockGetMemoryGuardianOverview.mockResolvedValue({
      ...baseOverview,
      alerts: {
        guard_unavailable: {
          active: true,
          escalated: false,
          window_hours: 24,
          total: 2,
          reasons: {
            active_session_guard_unavailable: 2,
          },
          dominant_reason: 'active_session_guard_unavailable',
          dominant_reason_count: 2,
          dominant_reason_ratio: 1,
          thresholds: undefined,
          last_occurred_at: '2026-07-18T00:00:00+00:00',
        },
      },
    });

    render(<MemoryGuardianCard />);

    await waitFor(() => {
      expect(mockGetMemoryGuardianOverview).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/guardAlertObservedDetail/)).toBeInTheDocument();
    expect(screen.queryByText(/guardAlertThresholdDetail/)).not.toBeInTheDocument();
    expect(screen.getByText('guardAlertMonitoringHint')).toBeInTheDocument();
  });
});
