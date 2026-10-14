/**
 * Regression tests for how the proposal card explains a held proposal: scan findings and risk signals are shown
 * in the user's language, never as internal codes, and the advice is derived from the signals themselves.
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
    id: 'draft:case-risk-1',
    source: 'draft',
    status: 'PENDING_REVIEW',
    skillName: 'weekly-report-upload',
    skillId: null,
    growthType: 'skill_draft',
    title: 'weekly-report-upload',
    summary: 'Build and share the weekly report.',
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

const scanCopy = en.settings.skills.scanRisk;

describe('SkillGrowthCaseCard held-for-review explanation', () => {
  it('words each risk signal in plain language and derives the advice from the signals', () => {
    renderCard(
      makeItem({
        reasonCode: 'risk:new_high_finding:data_exfiltration,diff_range:73%',
        remediation: 'The change adds high-risk behavior — review the flagged lines before approving.',
      }),
    );

    expect(screen.getByText(`New high-risk behavior: ${scanCopy.threat.data_exfiltration}`)).toBeInTheDocument();
    expect(screen.getByText('Large rewrite (73% changed)')).toBeInTheDocument();
    expect(
      screen.getByText(`${scanCopy.remediation.newHighFinding} ${scanCopy.remediation.diffRange}`),
    ).toBeInTheDocument();
    expect(screen.queryByText(/new_high_finding|diff_range|data_exfiltration/)).toBeNull();
    expect(screen.queryByText(/review the flagged lines before approving\./)).toBeNull();
  });

  it('explains a held draft whose scan could not run', () => {
    renderCard(makeItem({ reasonCode: 'risk:scan_unavailable' }));

    expect(screen.getByText(scanCopy.signal.scanUnavailable)).toBeInTheDocument();
    expect(screen.getByText(scanCopy.remediation.scanUnavailable)).toBeInTheDocument();
    expect(screen.queryByText(/scan_unavailable/)).toBeNull();
  });

  it('shows a generic label and no advice for a signal it does not recognise', () => {
    renderCard(makeItem({ reasonCode: 'risk:something_new:42' }));

    expect(screen.getByText(scanCopy.signal.unknown)).toBeInTheDocument();
    expect(screen.queryByText(/something_new/)).toBeNull();
    expect(screen.queryByText(scanCopy.remediation.newHighFinding)).toBeNull();
  });

  it('shows no risk panel for other reason codes', () => {
    renderCard(makeItem({ reasonCode: 'manual_review' }));

    expect(screen.queryByText(en.settings.skills.growth.riskInterceptionTitle)).toBeNull();
  });

  it('names scan findings by threat class and severity instead of their codes', () => {
    renderCard(
      makeItem({
        securityScanSummary: {
          score: 60,
          trust_recommendation: 'untrusted',
          total_findings: 2,
          findings: [
            {
              threat_type: 'data_exfiltration',
              severity: 'high',
              description: 'Data exfiltration: webhook upload',
              line_number: 3,
            },
            { threat_type: 'brand_new_class', severity: 'medium', description: 'Something unusual', line_number: null },
          ],
        },
      }),
    );

    expect(screen.getByText(scanCopy.threat.data_exfiltration)).toBeInTheDocument();
    expect(screen.getByText(scanCopy.threat.unknown)).toBeInTheDocument();
    expect(screen.getByText(scanCopy.severity.high)).toBeInTheDocument();
    expect(screen.getByText(scanCopy.severity.medium)).toBeInTheDocument();
    expect(screen.queryByText(/brand_new_class|^data_exfiltration$/)).toBeNull();
  });
});
