/**
 * Regression tests for SkillGrowthCaseCard verification record rendering and the view-mode split of developer diagnostics.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en.json';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const TRANSLATIONS: Record<string, string> = {
  'settings.skills.growth.verifiedBadge': 'Verified',
  'settings.skills.growth.hollowBlockedBadge': 'Hollow Test Blocked',
  'settings.skills.growth.verificationProofTitle': 'Verification record',
  'settings.skills.growth.targetLayer': 'Layer',
  'settings.skills.growth.targetPathology': 'Pathology',
  'settings.skills.growth.source.backgroundReview': 'Background Review',
  'settings.skills.growth.status.PENDING_REVIEW': 'Pending Review',
};

const growthTypeNames: Record<string, string> = en.growthDashboard.growthTypes;
const growthTypeT = Object.assign((key: string) => growthTypeNames[key] ?? key, {
  has: (key: string) => key in growthTypeNames,
});

const stableT = (key: string, params?: Record<string, unknown>): string => {
  if (key === 'blastRadius' && params) {
    return `Blast Radius: ${params.files} file(s), ${params.lines} line(s)`;
  }
  return TRANSLATIONS[key] ?? TRANSLATIONS[`settings.skills.growth.${key}`] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (namespace === 'growthDashboard.growthTypes' ? growthTypeT : stableT),
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
    id: 'case-proof-1',
    source: 'draft',
    status: 'PENDING_REVIEW',
    skillName: 'capsule-proof-skill',
    skillId: null,
    growthType: 'skill_patch',
    title: 'capsule-proof-skill',
    summary: 'A verified capsule test skill',
    description: null,
    confidence: 0.95,
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
    createdAt: '2026-08-27T12:00:00Z',
    impactedDependents: [],
    verificationProof: null,
    ...overrides,
  };
}

describe('SkillGrowthCaseCard verification record', () => {
  it('renders verified badge and verification record details when is_verified is true', () => {
    const item = makeItem({
      verificationProof: {
        is_verified: true,
        hollow_detected: false,
        blast_radius: { files: 1, lines: 18 },
        verification_summary: 'Passed AST check and sandbox tests cleanly',
      },
    });

    render(
      <SkillGrowthCaseCard
        item={item}
        isProcessing={false}
        viewMode="detailed"
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText('Verification record')).toBeInTheDocument();
    expect(screen.getByText('Passed AST check and sandbox tests cleanly')).toBeInTheDocument();
    expect(screen.getByText('Blast Radius: 1 file(s), 18 line(s)')).toBeInTheDocument();
  });

  it('renders hollow blocked badge when hollow_detected is true', () => {
    const item = makeItem({
      verificationProof: {
        is_verified: false,
        hollow_detected: true,
        blast_radius: { files: 1, lines: 5 },
        verification_summary: 'Hollow Test Rejected: Trivial assertion detected',
      },
    });

    render(
      <SkillGrowthCaseCard
        item={item}
        isProcessing={false}
        viewMode="detailed"
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.getByText('Hollow Test Blocked')).toBeInTheDocument();
  });

  it.each([
    ['simple', false],
    ['detailed', true],
  ] as const)('shows layer and pathology diagnostics only in detailed mode (%s)', (viewMode, visible) => {
    render(
      <SkillGrowthCaseCard
        item={makeItem({ targetLayer: 'L2', targetPathology: 'tool_misuse' })}
        isProcessing={false}
        viewMode={viewMode}
        onApprove={async () => {}}
        onReject={async () => {}}
      />,
    );

    expect(screen.queryByText('Layer') !== null).toBe(visible);
    expect(screen.queryByText('Pathology') !== null).toBe(visible);
  });
});
