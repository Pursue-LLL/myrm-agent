/**
 * Regression tests for the toast shown when approving a proposal could not be applied: it names the cause in the
 * user's language from the server's stable reason code and never surfaces the raw error text.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import { PendingEvolutionsDashboard } from '../PendingEvolutionsDashboard';
import { SCAN_RISK_NAMESPACE, scanRiskT } from './scanRiskTranslator';
import type { SkillGrowthActionResult, SkillGrowthCaseSummary } from '@/services/skill/growth';

const mocks = vi.hoisted(() => ({
  approveSkillGrowthCase: vi.fn(),
  listSkillGrowthCases: vi.fn(),
  getSkillGrowthSummary: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  // Stable identities, like the store's real actions: the dashboard reloads its list whenever they change between renders.
  fetchLocalSkills: vi.fn(),
  fetchUserSkillConfig: vi.fn(),
}));

const growthCopy = en.settings.skills.growth;

const growthT = (key: string, values?: Record<string, string | number>): string => {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], growthCopy);
  if (typeof value !== 'string') {
    return key;
  }
  return value.replace(/\{(\w+)\}/g, (_, name: string) => String(values?.[name] ?? `{${name}}`));
};

const growthTypeNames: Record<string, string> = en.growthDashboard.growthTypes;
const growthTypeT = Object.assign((key: string) => growthTypeNames[key] ?? key, {
  has: (key: string) => key in growthTypeNames,
});

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => {
    if (namespace === 'growthDashboard.growthTypes') {
      return growthTypeT;
    }
    return namespace === SCAN_RISK_NAMESPACE ? scanRiskT : growthT;
  },
  useLocale: () => 'en',
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('@/services/skill/growth', () => ({
  approveSkillGrowthCase: mocks.approveSkillGrowthCase,
  listSkillGrowthCases: mocks.listSkillGrowthCases,
  getSkillGrowthSummary: mocks.getSkillGrowthSummary,
  rejectSkillGrowthCase: vi.fn(),
  reviseSkillGrowthCase: vi.fn(),
  getSkillGrowthCaseDetail: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: { error: mocks.toastError, success: mocks.toastSuccess },
}));

vi.mock('@/store/skill', () => ({
  useSkillStore: () => ({
    fetchLocalSkills: mocks.fetchLocalSkills,
    fetchUserSkillConfig: mocks.fetchUserSkillConfig,
  }),
}));

vi.mock('@/store/useAuthStore', () => ({
  default: () => ({ user: { id: 'user-1' } }),
}));

vi.mock('@/lib/diff/TextDiffViewer', () => ({ TextDiffViewer: () => <div /> }));
vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({ LazyMonacoDiffEditor: () => <div /> }));
vi.mock('@/hooks/ui/useMediaQuery', () => ({ useIsMobile: () => false }));

const RAW_ERROR = "OSError: [Errno 30] Read-only file system: '/data/skills/weekly-report-upload/SKILL.md'";

const pendingCase: SkillGrowthCaseSummary = {
  id: 'evolution:evo-1',
  source: 'evolution',
  status: 'PENDING_REVIEW',
  skillName: 'weekly-report-upload',
  skillId: 'skill-1',
  growthType: 'skill_fix',
  title: 'weekly-report-upload',
  summary: 'Fix the upload step.',
  description: null,
  confidence: null,
  applyStatus: null,
  applyError: null,
  reasonCode: null,
  remediation: null,
  runtimeFailure: null,
  chatId: null,
  hasDiff: false,
  hasTrajectory: false,
  hasTriggerCondition: false,
  hasSkillSteps: false,
  createdAt: '2026-10-14T12:00:00Z',
  impactedDependents: [],
  verificationProof: null,
};

function failedApply(reasonCode: string | null): SkillGrowthActionResult {
  return {
    status: 'apply_failed',
    skill_id: 'skill-1',
    apply_status: 'FAILED',
    apply_error: RAW_ERROR,
    reason_code: reasonCode,
    remediation: 'Fix the skill directory permissions, then approve again.',
  };
}

describe('PendingEvolutionsDashboard approve failure toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.fetchLocalSkills.mockResolvedValue(undefined);
    mocks.fetchUserSkillConfig.mockResolvedValue(undefined);
    mocks.listSkillGrowthCases.mockResolvedValue({ items: [pendingCase], total: 1 });
    mocks.getSkillGrowthSummary.mockResolvedValue({ total: 1, pendingReview: 1, autoApplied: 0, blocked: 0 });
  });

  async function approveWith(result: SkillGrowthActionResult): Promise<string> {
    mocks.approveSkillGrowthCase.mockResolvedValue(result);
    render(<PendingEvolutionsDashboard />);

    fireEvent.click(await screen.findByRole('button', { name: growthCopy.actions.approve }));

    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
    return mocks.toastError.mock.calls[0][0] as string;
  }

  it.each([
    ['stale_base', growthCopy.approveFailedStaleBase],
    ['skill_md_unloadable', growthCopy.approveFailedUnloadable],
    ['apply_failed', growthCopy.approveFailed],
    [null, growthCopy.approveFailed],
  ])('words reason code %s in the user language without the raw error', async (reasonCode, template) => {
    const message = await approveWith(failedApply(reasonCode));

    expect(message).toBe(template.replace('{name}', 'weekly-report-upload'));
    expect(message).not.toContain('OSError');
    expect(message).not.toContain('directory permissions');
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });
});
