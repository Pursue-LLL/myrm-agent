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
  'status.UNPROVEN': 'Unproven',
  recStar: 'Star asset in active rotation.',
  recAtRisk: 'High failure rate detected. Review prompt parameters.',
  recHealthy: 'Healthy asset in active rotation.',
  recStale: 'Skill has not been invoked. Consider deprecating.',
  recUnproven: 'Too early to judge: {observed} of {required} runs have a clear result so far.',
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
      last_used_at: '2026-09-08T00:00:00Z',
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
      last_used_at: '2026-09-08T01:00:00Z',
      actionable_recommendation: 'High failure rate detected. Review prompt parameters.',
    },
    {
      skill_name: 'dormant_script',
      health_score: 0.0,
      status: 'STALE',
      call_count_7d: 0,
      call_count_total: 0,
      observed_count_7d: 0,
      min_observed_count: 5,
      success_rate_7d: null,
      last_used_at: null,
      actionable_recommendation: 'Skill has not been invoked. Consider deprecating.',
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

  it('shows the success rate only for skills whose run outcomes were observed', () => {
    render(<SkillHealthPanel items={mockItems} />);

    expect(screen.getByText(/20 calls \(7D\) · 80 total · 100% success/)).toBeInTheDocument();
    expect(screen.getByText(/12 calls \(7D\) · 12 total · 45% success/)).toBeInTheDocument();
    expect(screen.getByText('0 calls (7D) · 0 total')).toBeInTheDocument();
    expect(screen.queryByText(/(?<!\d)0% success/)).not.toBeInTheDocument();
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
      last_used_at: '2026-09-08T00:00:00Z',
      actionable_recommendation: 'Too few observed outcomes to judge quality yet (1 of 5 needed).',
    };

    render(<SkillHealthPanel items={[unproven]} />);

    expect(screen.getByText('Unproven')).toBeInTheDocument();
    expect(screen.getByText('Too early to judge: 1 of 5 runs have a clear result so far.')).toBeInTheDocument();
    expect(screen.getByText('2 calls (7D) · 2 total')).toBeInTheDocument();
    expect(screen.getByText('–')).toBeInTheDocument();
    expect(screen.queryByText('20')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Needs Attention/i }));
    expect(screen.queryByText('fresh_skill')).not.toBeInTheDocument();
  });

  it('shows the backend wording for a status this build has no copy for instead of a wrong verdict', () => {
    const future: SkillHealthItem = {
      ...mockItems[0],
      skill_name: 'future_skill',
      status: 'QUARANTINED' as SkillHealthItem['status'],
      actionable_recommendation: 'Quarantined pending review.',
    };

    render(<SkillHealthPanel items={[future]} />);

    expect(screen.getByText('QUARANTINED')).toBeInTheDocument();
    expect(screen.getByText('Quarantined pending review.')).toBeInTheDocument();
    expect(screen.queryByText('Healthy asset in active rotation.')).not.toBeInTheDocument();
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
      observed_count_7d: 10,
      min_observed_count: 5,
      success_rate_7d: 0.9,
      last_used_at: '2026-09-08T00:00:00Z',
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
