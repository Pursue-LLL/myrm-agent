/**
 * Regression tests for how the proposal card explains a held proposal: scan findings and risk signals are shown
 * in the user's language, never as internal codes, and the advice is derived from the signals themselves.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import { SCAN_RISK_NAMESPACE, scanRiskT } from './scanRiskTranslator';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

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
    expect(screen.queryByText(growthCopy.heldReason.title)).toBeNull();
  });

  it('names the skills a draft was found similar to without exposing the code', () => {
    renderCard(makeItem({ reasonCode: 'similar:deploy-flow,release_notes' }));

    expect(screen.getByText(growthCopy.heldReason.title)).toBeInTheDocument();
    expect(
      screen.getByText(growthCopy.heldReason.similar.replace('{names}', 'deploy-flow, release_notes')),
    ).toBeInTheDocument();
    expect(screen.queryByText(/similar:/)).toBeNull();
  });

  it.each([
    ['scan_failed', growthCopy.heldReason.scanFailed],
    ['evolution_locked', growthCopy.heldReason.evolutionLocked],
  ])('explains %s in plain language', (reasonCode, sentence) => {
    renderCard(makeItem({ reasonCode }));

    expect(screen.getByText(sentence)).toBeInTheDocument();
    expect(screen.queryByText(reasonCode)).toBeNull();
  });

  it('keeps the apply error text behind the technical details', () => {
    renderCard(
      makeItem({
        reasonCode: 'apply_failed',
        applyError: "PermissionError: [Errno 13] Permission denied: '/data/skills/weekly-report-upload'",
        remediation: 'Fix the skill directory permissions, then approve again.',
      }),
    );

    expect(screen.getByText(growthCopy.applyFailureBody)).toBeInTheDocument();
    expect(screen.queryByText(/PermissionError/)).toBeNull();
    expect(screen.queryByText(/directory permissions/)).toBeNull();

    fireEvent.click(screen.getByText(growthCopy.technical.toggle));

    expect(screen.getByText(/PermissionError/)).toBeInTheDocument();
    expect(screen.getByText(/directory permissions/)).toBeInTheDocument();
  });

  it('shows runtime failure facts up front and the raw error signature only when expanded', () => {
    renderCard(
      makeItem({
        runtimeFailure: {
          source: 'tool',
          tool_name: 'web_fetch',
          error_signature: 'ConnectTimeout: upstream timed out after 30s',
          tool_args_hash: null,
          loop_kind: 'repeated_call',
          skill_version: null,
          attribution_confidence: 0.8,
          failure_count: 3,
          first_seen_at: '2026-10-14T11:00:00Z',
          last_seen_at: '2026-10-14T12:00:00Z',
          candidate_skill_names: [],
        },
      }),
    );

    expect(screen.getByText('Tool: web_fetch')).toBeInTheDocument();
    expect(screen.getByText('Failures: 3')).toBeInTheDocument();
    expect(screen.queryByText(/ConnectTimeout|repeated_call/)).toBeNull();

    fireEvent.click(screen.getByText(growthCopy.technical.toggle));

    expect(screen.getByText('repeated_call / ConnectTimeout: upstream timed out after 30s')).toBeInTheDocument();
  });

  it('shows no technical details when there is nothing technical to show', () => {
    renderCard(makeItem({ reasonCode: 'similar:deploy-flow' }));

    expect(screen.queryByText(growthCopy.technical.toggle)).toBeNull();
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
    expect(screen.queryByText(/webhook upload|Something unusual/)).toBeNull();

    fireEvent.click(screen.getByText(growthCopy.technical.toggle));

    expect(screen.getByText(/webhook upload/)).toBeInTheDocument();
    expect(screen.getByText(/Something unusual/)).toBeInTheDocument();
  });
});
