/**
 * Regression tests for the proposal card's scan outcome: only a scan that actually ran is reported,
 * and a blocked case is not described as a failed security scan.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const growthCopy: Record<string, unknown> = en.settings.skills.growth;

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
    id: 'case-scan-1',
    source: 'evolution',
    status: 'PENDING_REVIEW',
    skillName: 'scan-outcome-skill',
    skillId: 'skill-1',
    growthType: 'fix',
    title: 'scan-outcome-skill',
    summary: 'A skill fix proposal',
    description: null,
    confidence: 0.9,
    testPassed: null,
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

describe('SkillGrowthCaseCard scan outcome', () => {
  it('reports a passed security scan', () => {
    renderCard(makeItem({ testPassed: true }));

    expect(screen.getByText(en.settings.skills.growth.scanPassed)).toBeInTheDocument();
    expect(screen.queryByText(en.settings.skills.growth.scanFailed)).toBeNull();
  });

  it('reports a failed security scan', () => {
    renderCard(makeItem({ testPassed: false, status: 'FAILED_SCAN' }));

    expect(screen.getByText(en.settings.skills.growth.scanFailed)).toBeInTheDocument();
    expect(screen.queryByText(en.settings.skills.growth.scanPassed)).toBeNull();
  });

  it('claims nothing about scanning when no scan ran', () => {
    renderCard(makeItem({ testPassed: null, status: 'FAILED_SCAN' }));

    expect(screen.queryByText(en.settings.skills.growth.scanPassed)).toBeNull();
    expect(screen.queryByText(en.settings.skills.growth.scanFailed)).toBeNull();
  });

  it('labels the blocked status without calling it a security scan failure', () => {
    renderCard(makeItem({ testPassed: null, status: 'FAILED_SCAN' }));

    expect(screen.getByText(en.settings.skills.growth.status.FAILED_SCAN)).toBeInTheDocument();
    expect(en.settings.skills.growth.status.FAILED_SCAN.toLowerCase()).not.toContain('scan');
  });
});
