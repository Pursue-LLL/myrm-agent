/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SkillHealthPanel from '../SkillHealthPanel';
import type { SkillHealthItem } from '@/services/statistics';

const translationMap: Record<string, string> = {
  title: 'Skill Health (7D)',
  description: 'Compounding health scores from recent skill usage.',
  empty: 'No skill usage recorded yet.',
  calls7d: '{count} calls (7D)',
  callsTotal: '{count} total',
  successRate: '{rate}% success',
  filterAll: 'All',
  filterAttention: 'Needs Attention',
  filterHealthy: 'Healthy & Stars',
  noAttentionNeeded: 'No at-risk or stale skills requiring governance.',
  recommendationPrefix: 'Recommendation:',
  manageSkill: 'Manage',
  'status.STAR': 'Star',
  'status.HEALTHY': 'Healthy',
  'status.AT_RISK': 'At Risk',
  'status.STALE': 'Stale',
  recStar: 'Star asset in active rotation.',
  recAtRisk: 'High failure rate detected. Review prompt parameters.',
  recHealthy: 'Healthy asset in active rotation.',
  recStale: 'Skill has not been invoked. Consider deprecating.',
  showMore: 'Show all ({count})',
  showLess: 'Show less',
};

const stableT = (key: string, values?: Record<string, unknown>) => {
  let text = translationMap[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SkillHealthPanel', () => {
  const mockItems: SkillHealthItem[] = [
    {
      skill_name: 'super_search',
      health_score: 95.0,
      status: 'STAR',
      call_count_7d: 20,
      call_count_total: 80,
      success_rate_7d: 1.0,
      last_used_at: '2026-09-08T00:00:00Z',
      actionable_recommendation: 'Star asset in active rotation.',
      adoption_rate: 0.95,
      reuse_breadth: 0.8,
    },
    {
      skill_name: 'flaky_plugin',
      health_score: 40.0,
      status: 'AT_RISK',
      call_count_7d: 12,
      call_count_total: 12,
      success_rate_7d: 0.45,
      last_used_at: '2026-09-08T01:00:00Z',
      actionable_recommendation: 'High failure rate detected. Review prompt parameters.',
      adoption_rate: 0.3,
      reuse_breadth: 0.2,
    },
    {
      skill_name: 'dormant_script',
      health_score: 0.0,
      status: 'STALE',
      call_count_7d: 0,
      call_count_total: 0,
      success_rate_7d: 0.0,
      last_used_at: null,
      actionable_recommendation: 'Skill has not been invoked. Consider deprecating.',
      adoption_rate: 0.0,
      reuse_breadth: 0.0,
    },
  ];

  it('renders empty message when no skills provided', () => {
    render(<SkillHealthPanel items={[]} />);
    expect(screen.getByText('No skill usage recorded yet.')).toBeInTheDocument();
  });

  it('renders all skills by default with tabs and recommendations', () => {
    render(<SkillHealthPanel items={mockItems} />);

    // Verify all 3 skills are displayed
    expect(screen.getByText('super_search')).toBeInTheDocument();
    expect(screen.getByText('flaky_plugin')).toBeInTheDocument();
    expect(screen.getByText('dormant_script')).toBeInTheDocument();

    // Verify recommendations
    expect(screen.getByText('Star asset in active rotation.')).toBeInTheDocument();
    expect(screen.getByText('High failure rate detected. Review prompt parameters.')).toBeInTheDocument();
    expect(screen.getByText('Skill has not been invoked. Consider deprecating.')).toBeInTheDocument();

    // Verify attention counter badge is 2 (flaky_plugin + dormant_script)
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('filters to only attention items when Needs Attention tab clicked', () => {
    render(<SkillHealthPanel items={mockItems} />);

    const attentionTab = screen.getByRole('button', { name: /Needs Attention/i });
    fireEvent.click(attentionTab);

    // Attention items visible
    expect(screen.getByText('flaky_plugin')).toBeInTheDocument();
    expect(screen.getByText('dormant_script')).toBeInTheDocument();

    // Healthy/Star item hidden
    expect(screen.queryByText('super_search')).not.toBeInTheDocument();
  });

  it('filters to only healthy items when Healthy tab clicked', () => {
    render(<SkillHealthPanel items={mockItems} />);

    const healthyTab = screen.getByRole('button', { name: /Healthy & Stars/i });
    fireEvent.click(healthyTab);

    // Healthy/Star item visible
    expect(screen.getByText('super_search')).toBeInTheDocument();

    // Attention items hidden
    expect(screen.queryByText('flaky_plugin')).not.toBeInTheDocument();
    expect(screen.queryByText('dormant_script')).not.toBeInTheDocument();
  });

  it('supports expanding and collapsing when item count exceeds 8', () => {
    const manyItems: SkillHealthItem[] = Array.from({ length: 12 }, (_, i) => ({
      skill_name: `skill_${i}`,
      health_score: 85.0,
      status: 'HEALTHY' as const,
      call_count_7d: 10,
      call_count_total: 20,
      success_rate_7d: 0.9,
      last_used_at: '2026-09-08T00:00:00Z',
      actionable_recommendation: 'Healthy asset in active rotation.',
      adoption_rate: 0.8,
      reuse_breadth: 0.8,
    }));

    render(<SkillHealthPanel items={manyItems} />);

    // Initially displays only first 8
    expect(screen.getByText('skill_0')).toBeInTheDocument();
    expect(screen.getByText('skill_7')).toBeInTheDocument();
    expect(screen.queryByText('skill_8')).not.toBeInTheDocument();

    // Click show more
    const showMoreBtn = screen.getByRole('button', { name: /Show all \(12\)/i });
    fireEvent.click(showMoreBtn);

    // Now all 12 are visible
    expect(screen.getByText('skill_8')).toBeInTheDocument();
    expect(screen.getByText('skill_11')).toBeInTheDocument();

    // Click show less
    const showLessBtn = screen.getByRole('button', { name: /Show less/i });
    fireEvent.click(showLessBtn);
    expect(screen.queryByText('skill_8')).not.toBeInTheDocument();
  });
});
