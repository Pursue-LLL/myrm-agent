/**
 * Regression tests for rejecting a growth proposal: a new-skill draft is discarded in one click, while a
 * revision proposal still asks why, because only that rejection records a reason.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const growthCopy = en.settings.skills.growth;

const growthT = (key: string): string => {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], growthCopy);
  return typeof value === 'string' ? value : key;
};

const growthTypeNames: Record<string, string> = en.growthDashboard.growthTypes;
const growthTypeT = Object.assign((key: string) => growthTypeNames[key] ?? key, {
  has: (key: string) => key in growthTypeNames,
});

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (namespace === 'growthDashboard.growthTypes' ? growthTypeT : growthT),
  useLocale: () => 'en',
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light' }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('@/lib/diff/TextDiffViewer', () => ({
  TextDiffViewer: () => <div data-testid="diff-viewer" />,
}));

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoDiffEditor: () => <div data-testid="monaco" />,
}));

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

function makeItem(overrides: Partial<SkillGrowthCaseSummary>): SkillGrowthCaseSummary {
  return {
    id: 'draft:case-1',
    source: 'draft',
    status: 'PENDING_REVIEW',
    skillName: 'weekly-report',
    skillId: null,
    growthType: 'skill_draft',
    title: 'weekly-report',
    summary: 'Build the weekly report.',
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
    ...overrides,
  };
}

function renderCard(item: SkillGrowthCaseSummary, onReject: (reason?: string) => Promise<void>): void {
  render(
    <SkillGrowthCaseCard
      item={item}
      isProcessing={false}
      viewMode="detailed"
      onApprove={async () => {}}
      onReject={onReject}
    />,
  );
}

describe('SkillGrowthCaseCard rejection', () => {
  it('discards a new-skill draft in one click without asking for a reason', async () => {
    const onReject = vi.fn(async () => {});
    renderCard(makeItem({ source: 'draft' }), onReject);

    fireEvent.click(screen.getByRole('button', { name: growthCopy.actions.reject }));

    await waitFor(() => expect(onReject).toHaveBeenCalledTimes(1));
    expect(onReject).toHaveBeenCalledWith(undefined);
    expect(screen.queryByLabelText(growthCopy.rejectReasonLabel)).toBeNull();
  });

  it('asks a revision proposal for a reason before rejecting and passes it along', async () => {
    const onReject = vi.fn(async () => {});
    renderCard(makeItem({ id: 'evolution:case-2', source: 'evolution', growthType: 'skill_patch' }), onReject);

    fireEvent.click(screen.getByRole('button', { name: growthCopy.actions.reject }));
    expect(onReject).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText(growthCopy.rejectReasonPlaceholder), {
      target: { value: '  too broad  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: growthCopy.actions.confirmReject }));

    await waitFor(() => expect(onReject).toHaveBeenCalledWith('too broad'));
  });
});
