/**
 * Regression tests for the hooks the evolution proposal review Chrome E2E drives: the card names its case and
 * status, and the two decision buttons are addressable, until the case is decided.
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
    status: 'PENDING_REVIEW',
    skillName: 'weekly-report',
    skillId: null,
    growthType: 'skill_patch',
    title: 'weekly-report',
    summary: 'Add a step to the weekly report.',
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

function renderCard(item: SkillGrowthCaseSummary): void {
  render(
    <SkillGrowthCaseCard
      item={item}
      isProcessing={false}
      viewMode="detailed"
      onApprove={async () => {}}
      onReject={async () => {}}
    />,
  );
}

describe('SkillGrowthCaseCard test hooks', () => {
  it('names the case and its status and marks the approve and reject buttons while the case awaits review', () => {
    renderCard(makeItem({}));

    const card = screen.getByTestId('growth-case-card');
    expect(card.getAttribute('data-case-id')).toBe('evolution:case-1');
    expect(card.getAttribute('data-case-status')).toBe('PENDING_REVIEW');
    expect(screen.getByTestId('growth-case-approve-btn').textContent).toBe(growthCopy.actions.approve);
    expect(screen.getByTestId('growth-case-reject-btn').textContent).toBe(growthCopy.actions.reject);
  });

  it('keeps the status on the card but offers no decision once the case is approved', () => {
    renderCard(makeItem({ status: 'APPROVED', applyStatus: 'APPLIED' }));

    expect(screen.getByTestId('growth-case-card').getAttribute('data-case-status')).toBe('APPROVED');
    expect(screen.queryByTestId('growth-case-approve-btn')).toBeNull();
    expect(screen.queryByTestId('growth-case-reject-btn')).toBeNull();
  });
});
