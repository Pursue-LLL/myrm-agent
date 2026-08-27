/**
 * Regression tests for SkillGrowthCaseCard Verified Badge and Capsule Proof rendering.
 */
/** @vitest-environment jsdom */

import type React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SkillGrowthCaseCard from '../SkillGrowthCaseCard';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

const TRANSLATIONS: Record<string, string> = {
  'settings.skills.growth.verifiedBadge': 'Verified (Streak: 3)',
  'settings.skills.growth.hollowBlockedBadge': 'Hollow Test Blocked',
  'settings.skills.growth.verificationProofTitle': 'Verified Capsule Proof',
  'settings.skills.growth.source.backgroundReview': 'Background Review',
  'settings.skills.growth.status.PENDING_REVIEW': 'Pending Review',
};

const stableT = (key: string, params?: Record<string, unknown>): string => {
  if (key === 'verifiedBadge' && params?.streak) {
    return `Verified (Streak: ${params.streak})`;
  }
  if (key === 'blastRadius' && params) {
    return `Blast Radius: ${params.files} file(s), ${params.lines} line(s)`;
  }
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
    createdAt: '2026-08-27T12:00:00Z',
    impactedDependents: [],
    verificationProof: null,
    ...overrides,
  };
}

describe('SkillGrowthCaseCard Verified Capsule Proof', () => {
  it('renders verified badge and capsule proof details when is_verified is true', () => {
    const item = makeItem({
      verificationProof: {
        is_verified: true,
        hollow_detected: false,
        success_streak: 3,
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

    expect(screen.getByText('Verified (Streak: 3)')).toBeInTheDocument();
    expect(screen.getByText('Verified Capsule Proof')).toBeInTheDocument();
    expect(screen.getByText('Passed AST check and sandbox tests cleanly')).toBeInTheDocument();
    expect(screen.getByText('Blast Radius: 1 file(s), 18 line(s)')).toBeInTheDocument();
  });

  it('renders hollow blocked badge when hollow_detected is true', () => {
    const item = makeItem({
      verificationProof: {
        is_verified: false,
        hollow_detected: true,
        success_streak: 0,
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
});
