/** @vitest-environment jsdom */

import type React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockListSkillGrowthAudit = vi.hoisted(() => vi.fn());
const mockGetSkillGrowthAuditStats = vi.hoisted(() => vi.fn());
const mockToastError = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill/growth', () => ({
  listSkillGrowthAudit: mockListSkillGrowthAudit,
  getSkillGrowthAuditStats: mockGetSkillGrowthAuditStats,
}));

vi.mock('sonner', () => ({
  toast: { error: mockToastError },
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/lib/utils/localeText', () => ({
  localizeReactNode: (node: React.ReactNode) => node,
  selectLocalizedText: (value: string) => value,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

import { EvolutionRejectionDashboard } from '../EvolutionRejectionDashboard';

const makeEntry = (overrides: Record<string, unknown> = {}) => ({
  eventId: 'evt-1',
  caseId: 'case-1',
  source: 'draft',
  status: 'REJECTED',
  skillName: 'my-skill',
  skillId: 'skill-1',
  growthType: 'skill_draft',
  reason: 'not enough value',
  confidence: 0.42,
  severity: 'info',
  reasonCode: null,
  remediation: null,
  createdAt: '2026-08-01T00:00:00Z',
  ...overrides,
});

const makeStats = (overrides: Record<string, unknown> = {}) => ({
  totalEvents: 1,
  avgConfidence: 0.42,
  byStatus: [{ key: 'REJECTED', count: 1, percentage: 100 }],
  topSkills: [],
  timeRangeDays: 30,
  ...overrides,
});

describe('EvolutionRejectionDashboard SSE refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockListSkillGrowthAudit.mockResolvedValue([makeEntry()]);
    mockGetSkillGrowthAuditStats.mockResolvedValue(makeStats());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('listens to skill-growth-updated and refetches entries + stats', async () => {
    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(1);
      expect(mockGetSkillGrowthAuditStats).toHaveBeenCalledTimes(1);
    });

    mockListSkillGrowthAudit.mockResolvedValue([makeEntry({ status: 'FAILED_SCAN' })]);

    await act(async () => {
      window.dispatchEvent(new CustomEvent('skill-growth-updated'));
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(2);
      expect(mockGetSkillGrowthAuditStats).toHaveBeenCalledTimes(2);
    });
  });

  it('listens to app_resync_required as a refresh trigger too', async () => {
    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent('app_resync_required'));
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(2);
    });
  });

  it('debounces rapid repeated events into a single refetch', async () => {
    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent('skill-growth-updated'));
      window.dispatchEvent(new CustomEvent('skill-growth-updated'));
      window.dispatchEvent(new CustomEvent('skill-growth-updated'));
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(2);
    });
  });

  it('removes event listeners on unmount', async () => {
    const { unmount } = render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(1);
    });

    unmount();

    await act(async () => {
      window.dispatchEvent(new CustomEvent('skill-growth-updated'));
      vi.advanceTimersByTime(1100);
    });

    expect(mockListSkillGrowthAudit).toHaveBeenCalledTimes(1);
  });

  it('shows an error toast when the audit list request fails', async () => {
    mockListSkillGrowthAudit.mockRejectedValue(new Error('network down'));

    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalled();
    });
  });

  it('renders an empty state when there are no entries', async () => {
    mockListSkillGrowthAudit.mockResolvedValue([]);
    mockGetSkillGrowthAuditStats.mockResolvedValue(makeStats({ totalEvents: 0, byStatus: [] }));

    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(screen.getByText('noLogs')).toBeInTheDocument();
    });
  });

  it('displays audit entries in the table after load', async () => {
    render(<EvolutionRejectionDashboard />);

    await waitFor(() => {
      expect(screen.getByText('my-skill')).toBeInTheDocument();
    });
  });
});
