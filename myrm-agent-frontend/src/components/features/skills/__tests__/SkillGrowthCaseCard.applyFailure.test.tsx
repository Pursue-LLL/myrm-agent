/**
 * Regression tests for the actions a growth card offers after applying an approved proposal failed: only those that
 * can change the outcome. A skill edited since the proposal was made fails again on retry and on revise, so only
 * rejecting resolves it; an unloadable proposal fails again on retry, so it can be revised or rejected.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
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
    id: 'evolution:case-1',
    source: 'evolution',
    status: 'APPLY_FAILED',
    skillName: 'weekly-report',
    skillId: 'skill-1',
    growthType: 'skill_fix',
    title: 'weekly-report',
    summary: 'Fix the upload step.',
    description: null,
    confidence: null,
    applyStatus: 'FAILED',
    applyError: 'The skill file changed after this proposal was created.',
    reasonCode: 'apply_failed',
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

function renderCard(item: SkillGrowthCaseSummary): void {
  render(
    <SkillGrowthCaseCard
      item={item}
      isProcessing={false}
      viewMode="detailed"
      onApprove={async () => {}}
      onReject={async () => {}}
      onRevise={async () => {}}
    />,
  );
}

const hasAction = (name: string): boolean => screen.queryByRole('button', { name }) !== null;

describe('SkillGrowthCaseCard actions after a failed apply', () => {
  it('offers only rejecting when the skill changed since the proposal was made', () => {
    renderCard(makeItem({ reasonCode: 'stale_base' }));

    expect(hasAction(growthCopy.actions.reject)).toBe(true);
    expect(hasAction(growthCopy.actions.retryApply)).toBe(false);
    expect(hasAction(growthCopy.actions.revise)).toBe(false);
  });

  it('offers revising or rejecting, not retrying, when the proposed file is not a valid skill', () => {
    renderCard(makeItem({ reasonCode: 'skill_md_unloadable' }));

    expect(hasAction(growthCopy.actions.reject)).toBe(true);
    expect(hasAction(growthCopy.actions.revise)).toBe(true);
    expect(hasAction(growthCopy.actions.retryApply)).toBe(false);
  });

  it.each(['apply_failed', null])('keeps retry, revise and reject for other failures (reason %s)', (reasonCode) => {
    renderCard(makeItem({ reasonCode }));

    expect(hasAction(growthCopy.actions.retryApply)).toBe(true);
    expect(hasAction(growthCopy.actions.revise)).toBe(true);
    expect(hasAction(growthCopy.actions.reject)).toBe(true);
  });

  it('keeps approve, revise and reject for a proposal still waiting for review', () => {
    renderCard(makeItem({ status: 'PENDING_REVIEW', applyStatus: null, applyError: null, reasonCode: null }));

    expect(hasAction(growthCopy.actions.approve)).toBe(true);
    expect(hasAction(growthCopy.actions.revise)).toBe(true);
    expect(hasAction(growthCopy.actions.reject)).toBe(true);
  });
});
