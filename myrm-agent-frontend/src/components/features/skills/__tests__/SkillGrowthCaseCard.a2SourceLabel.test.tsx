/**
 * A2 回归：SkillGrowthCaseCard 三元 sourceLabel 与 growthType 徽章隐藏。
 * - evolution source → 手动进化（manualEvolution）
 * - semantic_memory growthType → 记忆提取（memoryExtraction）
 * - 其它 draft → 后台复盘（backgroundReview）
 * - semantic_memory case 不渲染 growthType 徽章（TOC 不泄漏技术细节）
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
    id: 'case-1',
    source: 'draft',
    status: 'PENDING_REVIEW',
    skillName: 'demo-skill',
    skillId: null,
    growthType: 'skill_draft',
    title: 'Demo draft',
    summary: 'A proposal',
    description: null,
    confidence: 0.9,
    testPassed: null,
    applyStatus: null,
    applyError: null,
    reasonCode: null,
    remediation: null,
    runtimeFailure: null,
    chatId: 'chat-1',
    formMetadata: null,
    hasDiff: false,
    hasTrajectory: false,
    hasTriggerCondition: false,
    hasSkillSteps: false,
    createdAt: '2026-08-10T00:00:00Z',
    impactedDependents: [],
    ...overrides,
  };
}

const noop = async (): Promise<void> => {};

describe('SkillGrowthCaseCard A2 source label', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('evolution source renders "Manual Evolution" label', () => {
    render(
      <SkillGrowthCaseCard
        item={makeItem({ source: 'evolution' })}
        isProcessing={false}
        onApprove={noop}
        onReject={noop}
      />,
    );
    expect(screen.getByText('Manual Evolution')).toBeInTheDocument();
  });

  it('continual source renders "Continual Recovery" label', () => {
    render(
      <SkillGrowthCaseCard
        item={makeItem({ source: 'continual' })}
        isProcessing={false}
        onApprove={noop}
        onReject={noop}
      />,
    );
    expect(screen.getByText('Continual Recovery')).toBeInTheDocument();
  });

  it('semantic_memory growthType renders "Memory Extraction" label without growthType badge', () => {
    render(
      <SkillGrowthCaseCard
        item={makeItem({ source: 'draft', growthType: 'semantic_memory' })}
        isProcessing={false}
        onApprove={noop}
        onReject={noop}
      />,
    );
    expect(screen.getByText('Memory Extraction')).toBeInTheDocument();
    expect(screen.queryByText('semantic_memory')).not.toBeInTheDocument();
  });

  it('plain draft renders "Background Review" label with growthType badge visible', () => {
    render(
      <SkillGrowthCaseCard
        item={makeItem({ source: 'draft', growthType: 'skill_draft' })}
        isProcessing={false}
        onApprove={noop}
        onReject={noop}
      />,
    );
    expect(screen.getByText('Background Review')).toBeInTheDocument();
    expect(screen.getByText('skill_draft')).toBeInTheDocument();
  });
});
