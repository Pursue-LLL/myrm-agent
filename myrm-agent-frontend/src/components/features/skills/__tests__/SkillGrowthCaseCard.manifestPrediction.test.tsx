/**
 * Tests for SkillGrowthCaseCard Change Manifest Predictions & Attribution Rendering.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const TRANSLATIONS: Record<string, string> = {
  'settings.skills.growth.manifestPrediction.title': 'Change Manifest Predictions & Attribution',
  'settings.skills.growth.manifestPrediction.baseline': 'Baseline',
  'settings.skills.growth.manifestPrediction.target': 'Target',
  'settings.skills.growth.manifestPrediction.verdictBadge.CONFIRMED': 'CONFIRMED',
  'settings.skills.growth.manifestPrediction.verdictBadge.REGRESSION': 'REGRESSION',
  'settings.skills.growth.manifestPrediction.falsificationConditions': 'Falsification Conditions',
  'settings.skills.growth.manifestPrediction.unpredictedRegressions': 'Unpredicted Regressions',
  'settings.skills.growth.source.manualEvolution': 'Manual Evolution',
  'settings.skills.growth.status.PENDING_REVIEW': 'Pending Review',
};

const stableT = (key: string, _params?: Record<string, unknown>): string => {
  return TRANSLATIONS[key] ?? TRANSLATIONS[`settings.skills.growth.${key}`] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
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
    id: 'case-manifest-1',
    source: 'evolution',
    status: 'PENDING_REVIEW',
    skillName: 'manifest_skill',
    skillId: 'sk-manifest',
    growthType: 'fix',
    title: 'Fix Assertion in Skill',
    summary: 'Proposes regex assertion fix',
    description: null,
    confidence: 0.9,
    testPassed: true,
    applyStatus: null,
    applyError: null,
    reasonCode: null,
    remediation: null,
    runtimeFailure: null,
    chatId: null,
    formMetadata: null,
    hasDiff: true,
    hasTrajectory: false,
    hasTriggerCondition: false,
    hasSkillSteps: false,
    createdAt: '2026-09-01T10:00:00.000Z',
    impactedDependents: [],
    verificationProof: null,
    ...overrides,
  };
}

describe('SkillGrowthCaseCard manifest prediction rendering', () => {
  it('renders prediction manifest metrics and rationale', () => {
    const item = makeItem({
      predictionManifest: {
        manifest_id: 'man-123',
        change_id: 'chg-123',
        created_at: '2026-09-01T10:00:00.000Z',
        predictions: [
          {
            metric_name: 'pass_rate',
            direction: 'INCREASE',
            baseline_value: 0.0,
            target_value: 1.0,
            rationale: 'Passes all 3 assertions on fixed content',
          },
        ],
        falsification_conditions: ['pass_rate regresses below 0.00'],
      },
    });

    render(
      <SkillGrowthCaseCard
        item={item}
        isProcessing={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText('Change Manifest Predictions & Attribution')).toBeInTheDocument();
    expect(screen.getByText('pass_rate')).toBeInTheDocument();
    expect(screen.getByText(/Passes all 3 assertions on fixed content/)).toBeInTheDocument();
    expect(screen.getByText(/pass_rate regresses below 0.00/)).toBeInTheDocument();
  });

  it('renders attribution result verdict badge and details', () => {
    const item = makeItem({
      attributionResult: {
        manifest_id: 'man-123',
        verdict: 'CONFIRMED',
        attributed_at: '2026-09-01T10:05:00.000Z',
        metric_deltas: { pass_rate: 1.0 },
        unpredicted_regressions: [],
        details: 'Post-apply verification achieved 100% pass rate as predicted.',
      },
    });

    render(
      <SkillGrowthCaseCard
        item={item}
        isProcessing={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText('CONFIRMED')).toBeInTheDocument();
    expect(
      screen.getByText('Post-apply verification achieved 100% pass rate as predicted.')
    ).toBeInTheDocument();
  });
});
