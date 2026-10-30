/**
 * Regression tests for "Force Retry" in the evolution audit dashboard: a skill that is locked against automatic
 * changes is refused by the server, and the user is told in plain words how to proceed instead of seeing a generic
 * failure; the row only moves on when the retry was actually accepted.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

const mockListSkillGrowthAudit = vi.hoisted(() => vi.fn());
const mockGetSkillGrowthAuditStats = vi.hoisted(() => vi.fn());
const mockToastError = vi.hoisted(() => vi.fn());
const mockToastSuccess = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill/growth', () => ({
  listSkillGrowthAudit: mockListSkillGrowthAudit,
  getSkillGrowthAuditStats: mockGetSkillGrowthAuditStats,
}));

vi.mock('sonner', () => ({
  toast: { error: mockToastError, success: mockToastSuccess },
}));

const rejectionCopy: Record<string, unknown> = en.settingsTabs.evolutionRejection;
const growthTypeNames: Record<string, string> = en.growthDashboard.growthTypes;

function lookup(copy: Record<string, unknown>, key: string): string {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], copy);
  return typeof value === 'string' ? value : key;
}

const rejectionT = (key: string) => lookup(rejectionCopy, key);
const growthTypeT = Object.assign((key: string) => growthTypeNames[key] ?? key, {
  has: (key: string) => key in growthTypeNames,
});

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (namespace === 'settingsTabs.evolutionRejection' ? rejectionT : growthTypeT),
  useLocale: () => 'en',
}));

vi.mock('@/lib/utils/locale', () => ({
  localizeReactNode: (node: React.ReactNode) => node,
  selectLocalizedText: (value: string) => value,
}));

import { EvolutionRejectionDashboard } from '../EvolutionRejectionDashboard';

const entry = {
  eventId: 'evt-1',
  caseId: 'case-1',
  source: 'evolution',
  status: 'BLOCKED_LOCKED',
  skillName: 'my-skill',
  skillId: 'local::abc',
  growthType: 'skill_fix',
  reason: 'evolution_locked',
  confidence: 0.4,
  severity: 'info',
  reasonCode: null,
  remediation: null,
  createdAt: '2026-08-01T00:00:00Z',
};

const stats = { totalEvents: 1, avgConfidence: 0.4, byStatus: [], topSkills: [], timeRangeDays: 30 };

const forceRetryButton = () => screen.getByRole('button', { name: en.settingsTabs.evolutionRejection.forceRetry });

function stubFixResponse(status: number) {
  const fetchMock = vi.fn(
    async () => new Response(JSON.stringify({ detail: 'Skill is evolution-locked' }), { status }),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function renderAndForceRetry() {
  render(<EvolutionRejectionDashboard />);
  await waitFor(() => expect(screen.getByText('my-skill')).toBeInTheDocument());
  fireEvent.click(forceRetryButton());
}

describe('EvolutionRejectionDashboard force retry', () => {
  beforeEach(() => {
    mockListSkillGrowthAudit.mockResolvedValue([entry]);
    mockGetSkillGrowthAuditStats.mockResolvedValue(stats);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('explains how to proceed when the skill is locked, and keeps the row as it was', async () => {
    const fetchMock = stubFixResponse(409);

    await renderAndForceRetry();

    await waitFor(() => expect(mockToastError).toHaveBeenCalledTimes(1));
    const hint = en.settingsTabs.evolutionRejection.forceRetryLocked;
    expect(mockToastError).toHaveBeenCalledWith(hint);
    expect(hint).not.toMatch(/409|HTTP|force_retry|evolution_locked|status/i);
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/evolution/fix/local::abc',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(screen.getByText(en.settingsTabs.evolutionRejection.status.BLOCKED_LOCKED)).toBeInTheDocument();
    expect(forceRetryButton()).toBeEnabled();
  });

  it('reports any other refusal as a plain failure', async () => {
    stubFixResponse(500);

    await renderAndForceRetry();

    await waitFor(() => expect(mockToastError).toHaveBeenCalledTimes(1));
    expect(mockToastError).toHaveBeenCalledWith('重试失败 / Retry failed');
    expect(screen.getByText(en.settingsTabs.evolutionRejection.status.BLOCKED_LOCKED)).toBeInTheDocument();
  });

  it('moves the row to pending review once the retry is accepted', async () => {
    stubFixResponse(200);

    await renderAndForceRetry();

    await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledTimes(1));
    expect(mockToastError).not.toHaveBeenCalled();
    expect(screen.getByText(en.settingsTabs.evolutionRejection.status.PENDING_REVIEW)).toBeInTheDocument();
  });
});
