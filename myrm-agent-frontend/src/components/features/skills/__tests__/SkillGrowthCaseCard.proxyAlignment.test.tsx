/**
 * Tests for SkillGrowthCaseCard proxyAlignment badge rendering.
 * Verifies Goodhart drift warning badge and aligned badge.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const TRANSLATIONS: Record<string, string> = {
  'settings.skills.growth.source.manualEvolution': 'Manual Evolution',
  'settings.skills.growth.source.memoryExtraction': 'Memory Extraction',
  'settings.skills.growth.source.backgroundReview': 'Background Review',
  'settings.skills.growth.source.continualRecovery': 'Continual Recovery',
  'settings.skills.growth.proxyAlignment.driftBadge': 'Goodhart Drift Risk',
  'settings.skills.growth.proxyAlignment.driftTooltip': 'Goodhart drift detected',
  'settings.skills.growth.proxyAlignment.alignedBadge': 'Metrics Aligned',
  'settings.skills.growth.proxyAlignment.alignedTooltip': 'Metrics well aligned',
};

const stableT = (key: string): string => {
  const shortKey = key.replace(/^settings\.skills\.growth\./, '');
  return TRANSLATIONS[`settings.skills.growth.${shortKey}`] ?? `__${key}__`;
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
    id: 'test-1',
    source: 'evolution',
    status: 'PENDING_REVIEW',
    skillName: 'demo-skill',
    skillId: null,
    growthType: 'rule',
    title: 'demo-skill',
    summary: 'Summary text',
    description: 'Description text',
    confidence: 0.9,
    testPassed: true,
    applyStatus: null,
    applyError: null,
    reasonCode: null,
    remediation: null,
    runtimeFailure: null,
    chatId: null,
    formMetadata: null,
    hasDiff: false,
    hasTrajectory: false,
    hasTriggerCondition: false,
    hasSkillSteps: false,
    createdAt: new Date().toISOString(),
    impactedDependents: [],
    verificationProof: null,
    targetLayer: null,
    targetPathology: null,
    predictionManifest: null,
    attributionResult: null,
    proxyAlignment: null,
    ...overrides,
  };
}

describe('SkillGrowthCaseCard Proxy Alignment Badges', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Goodhart drift warning badge when verdict is goodhart_drift', () => {
    const item = makeItem({
      proxyAlignment: {
        contract_id: 'default',
        verdict: 'goodhart_drift',
        sample_size: 10,
        intent_delta: -0.2,
        proxy_improvement: 0.4,
        flagged_proxies: ['tokens'],
        warning_message: 'Goodhart drift detected on tokens',
      },
    });

    render(<SkillGrowthCaseCard item={item} isSimple={true} />);

    expect(screen.getByText('Goodhart Drift Risk')).toBeInTheDocument();
  });

  it('renders aligned badge when verdict is aligned', () => {
    const item = makeItem({
      proxyAlignment: {
        contract_id: 'default',
        verdict: 'aligned',
        sample_size: 10,
        intent_delta: 0.15,
        proxy_improvement: 0.25,
        flagged_proxies: [],
        warning_message: 'Metrics well aligned',
      },
    });

    render(<SkillGrowthCaseCard item={item} isSimple={true} />);

    expect(screen.getByText('Metrics Aligned')).toBeInTheDocument();
  });
});
