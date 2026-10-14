/**
 * Regression tests for the proposal card's security indicator: it reads the recorded scan summary,
 * speaks in user-facing risk wording, and a blocked case is not described as a failed security scan.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import { SCAN_RISK_NAMESPACE, scanRiskT } from './scanRiskTranslator';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const growthCopy: Record<string, unknown> = en.settings.skills.growth;

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

const securityCopy = en.settings.skills.growth.securityScan;

describe('SkillGrowthCaseCard security indicator', () => {
  it.each([
    ['trusted', 100, securityCopy.risk.trusted],
    ['installed', 75, securityCopy.risk.installed],
    ['untrusted', 55, securityCopy.risk.untrusted],
    ['reject', 20, securityCopy.risk.reject],
  ])('shows the %s level as plain risk wording with a localized tooltip', (trust, score, label) => {
    renderCard(makeItem({ securityScanSummary: { score, trust_recommendation: trust } }));

    expect(screen.getByText(`${score}/100 · ${label}`)).toBeInTheDocument();
    expect(screen.getByTitle(securityCopy.badgeTitle.replace('{score}', String(score)))).toBeInTheDocument();
    expect(screen.queryByText((content) => content.includes(trust.toUpperCase()))).toBeNull();
  });

  it('shows only the score for a trust level it does not know', () => {
    renderCard(makeItem({ securityScanSummary: { score: 90, trust_recommendation: 'new-level' } }));

    expect(screen.getByText('90/100')).toBeInTheDocument();
    expect(screen.queryByText(/new-level/i)).toBeNull();
  });

  it('claims nothing about scanning when the case carries no scan summary', () => {
    renderCard(makeItem({ securityScanSummary: null }));

    expect(screen.queryByText(/\/100/)).toBeNull();
  });

  it('labels the blocked status without calling it a security scan failure', () => {
    renderCard(makeItem({ status: 'FAILED_SCAN' }));

    expect(screen.getByText(en.settings.skills.growth.status.FAILED_SCAN)).toBeInTheDocument();
    expect(en.settings.skills.growth.status.FAILED_SCAN.toLowerCase()).not.toContain('scan');
  });
});
