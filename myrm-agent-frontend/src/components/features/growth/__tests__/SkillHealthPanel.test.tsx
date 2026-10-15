/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SkillHealthPanel from '../SkillHealthPanel';
import type { SkillHealthItem } from '@/services/statistics';

const translationMap: Record<string, string> = {
  title: 'Skill Health (7D)',
  description: 'Compounding health scores from recent skill usage.',
  empty: 'No skills ran in the last 7 days.',
  calls7d: '{count} calls (7D)',
  callsTotal: '{count} total',
  successRate: '{rate}% success',
  filterAll: 'All',
  filterAttention: 'Needs Attention',
  filterHealthy: 'Healthy & Stars',
  noAttentionNeeded: 'No at-risk skills right now.',
  recommendationPrefix: 'Recommendation:',
  manageSkill: 'Manage',
  'status.STAR': 'Star',
  'status.HEALTHY': 'Healthy',
  'status.AT_RISK': 'At Risk',
  'status.UNPROVEN': 'Unproven',
  recStar: 'Star asset in active rotation.',
  recAtRisk: 'High failure rate detected. Review prompt parameters.',
  recHealthy: 'Healthy asset in active rotation.',
  recUnproven: 'Not enough runs with a clear result yet: {observed} of {required}.',
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
      observed_count_7d: 20,
      min_observed_count: 5,
      success_rate_7d: 1.0,
      truncated: false,
      actionable_recommendation: 'Star asset in active rotation.',
    },
    {
      skill_name: 'flaky_plugin',
      health_score: 40.0,
      status: 'AT_RISK',
      call_count_7d: 12,
      call_count_total: 12,
      observed_count_7d: 11,
      min_observed_count: 5,
      success_rate_7d: 0.45,
      truncated: false,
      actionable_recommendation: 'High failure rate detected. Review prompt parameters.',
    },
    {
      skill_name: 'steady_tool',
      health_score: 80.0,
      status: 'HEALTHY',
      call_count_7d: 9,
      call_count_total: 9,
      observed_count_7d: 9,
      min_observed_count: 5,
      success_rate_7d: 0.8,
      truncated: false,
      actionable_recommendation: 'Healthy asset in active rotation.',
    },
  ];

  it('renders empty message when no skills provided', () => {
    render(<SkillHealthPanel items={[]} />);
    expect(screen.getByText('No skills ran in the last 7 days.')).toBeInTheDocument();
  });

  it('renders all skills by default with tabs and recommendations', () => {
    render(<SkillHealthPanel items={mockItems} />);

    // Verify all 3 skills are displayed
    expect(screen.getByText('super_search')).toBeInTheDocument();
    expect(screen.getByText('flaky_plugin')).toBeInTheDocument();
    expect(screen.getByText('steady_tool')).toBeInTheDocument();

    // Verify recommendations
    expect(screen.getByText('Star asset in active rotation.')).toBeInTheDocument();
    expect(screen.getByText('High failure rate detected. Review prompt parameters.')).toBeInTheDocument();
    expect(screen.getByText('Healthy asset in active rotation.')).toBeInTheDocument();

    // Only the at-risk skill needs attention
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('links each skill to the installed skill list, filtered by its name', () => {
    render(<SkillHealthPanel items={[{ ...mockItems[0], skill_name: 'report & digest/v2' }]} />);

    expect(screen.getByRole('link', { name: /Manage/ })).toHaveAttribute(
      'href',
      '/settings/skills?search=report%20%26%20digest%2Fv2',
    );
  });

  it('shows the success rate only for skills whose run outcomes were observed', () => {
    render(<SkillHealthPanel items={mockItems} />);

    expect(screen.getByText(/20 calls \(7D\) · 80 total · 100% success/)).toBeInTheDocument();
    expect(screen.getByText(/12 calls \(7D\) · 12 total · 45% success/)).toBeInTheDocument();
    expect(screen.getByText(/9 calls \(7D\) · 9 total · 80% success/)).toBeInTheDocument();
  });

  it('reads the weekly run count as a lower bound for a skill whose history was cut', () => {
    const hourlyJob: SkillHealthItem = { ...mockItems[0], call_count_7d: 200, call_count_total: 336, truncated: true };

    render(<SkillHealthPanel items={[hourlyJob]} />);

    expect(screen.getByText(/200\+ calls \(7D\) · 336 total/)).toBeInTheDocument();
  });

  it('explains how many observed outcomes an unproven skill still needs and hides its rate', () => {
    const unproven: SkillHealthItem = {
      skill_name: 'fresh_skill',
      health_score: 20.0,
      status: 'UNPROVEN',
      call_count_7d: 2,
      call_count_total: 2,
      observed_count_7d: 1,
      min_observed_count: 5,
      success_rate_7d: null,
      truncated: false,
      actionable_recommendation: 'Too few observed outcomes to judge quality yet (1 of 5 needed).',
    };

    render(<SkillHealthPanel items={[unproven]} />);

    expect(screen.getByText('Unproven')).toBeInTheDocument();
    expect(screen.getByText('Not enough runs with a clear result yet: 1 of 5.')).toBeInTheDocument();
    expect(screen.getByText('2 calls (7D) · 2 total')).toBeInTheDocument();
    expect(screen.queryByText(/% success/)).not.toBeInTheDocument();
    expect(screen.getByText('–')).toBeInTheDocument();
    expect(screen.queryByText('20')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Needs Attention/i }));
    expect(screen.queryByText('fresh_skill')).not.toBeInTheDocument();
  });

  it('shows no status badge for a status this build has no copy for, and never a wrong verdict', () => {
    const future: SkillHealthItem = {
      ...mockItems[0],
      skill_name: 'future_skill',
      status: 'QUARANTINED' as SkillHealthItem['status'],
      actionable_recommendation: 'Quarantined pending review.',
    };

    render(<SkillHealthPanel items={[future]} />);

    expect(screen.queryByText('QUARANTINED')).not.toBeInTheDocument();
    expect(screen.getByText('Quarantined pending review.')).toBeInTheDocument();
    expect(screen.queryByText('Healthy asset in active rotation.')).not.toBeInTheDocument();
  });

  it('filters to only attention items when Needs Attention tab clicked', () => {
    render(<SkillHealthPanel items={mockItems} />);

    const attentionTab = screen.getByRole('button', { name: /Needs Attention/i });
    fireEvent.click(attentionTab);

    // Only the at-risk item is visible
    expect(screen.getByText('flaky_plugin')).toBeInTheDocument();
    expect(screen.queryByText('super_search')).not.toBeInTheDocument();
    expect(screen.queryByText('steady_tool')).not.toBeInTheDocument();
  });

  it('says so when no skill is at risk', () => {
    render(<SkillHealthPanel items={[mockItems[0]]} />);

    fireEvent.click(screen.getByRole('button', { name: /Needs Attention/i }));

    expect(screen.getByText('No at-risk skills right now.')).toBeInTheDocument();
  });

  it('filters to only healthy items when Healthy tab clicked', () => {
    render(<SkillHealthPanel items={mockItems} />);

    const healthyTab = screen.getByRole('button', { name: /Healthy & Stars/i });
    fireEvent.click(healthyTab);

    // Healthy and star items visible
    expect(screen.getByText('super_search')).toBeInTheDocument();
    expect(screen.getByText('steady_tool')).toBeInTheDocument();

    // The at-risk item is hidden
    expect(screen.queryByText('flaky_plugin')).not.toBeInTheDocument();
  });

  it('supports expanding and collapsing when item count exceeds 8', () => {
    const manyItems: SkillHealthItem[] = Array.from({ length: 12 }, (_, i) => ({
      skill_name: `skill_${i}`,
      health_score: 85.0,
      status: 'HEALTHY' as const,
      call_count_7d: 10,
      call_count_total: 20,
      observed_count_7d: 10,
      min_observed_count: 5,
      success_rate_7d: 0.9,
      truncated: false,
      actionable_recommendation: 'Healthy asset in active rotation.',
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
