import { describe, expect, it } from 'vitest';
import type { GrowthDashboardData, SkillHealthItem } from '@/services/statistics';
import { buildGrowthMarkdown, type GrowthMarkdownLabels } from '../growthMarkdownExport';

const labels: GrowthMarkdownLabels = {
  title: 'Journey',
  period: 'Period',
  memories: 'Memories',
  memoryCitations: 'Citations',
  conversations: 'Conversations',
  messages: 'Messages',
  cronJobs: 'Cron',
  toolCalls: 'Tool calls',
  savings: 'Savings',
  totalCost: 'Cost',
  skillHealth: 'Skill health',
  skillRow: (name, score, status, calls7d) => `${name}|${score}|${status}|${calls7d}`,
  generatedAt: 'generated',
};

const skill = (skill_name: string, status: string, health_score: number): SkillHealthItem => ({
  skill_name,
  health_score,
  status,
  call_count_7d: 6,
  call_count_total: 6,
  observed_count_7d: 6,
  min_observed_count: 5,
  success_rate_7d: null,
});

const dashboard = (skill_health: SkillHealthItem[]): GrowthDashboardData => ({
  snapshot: {
    total_memories: 0,
    memory_by_type: {},
    memory_week_delta: 0,
    total_skills: 0,
    total_evolutions: 0,
    evolutions_approved: 0,
    evolutions_rejected: 0,
    evolutions_pending: 0,
    evolutions_apply_failed: 0,
    active_days: 0,
    max_streak: 0,
    memory_health_score: 0,
    memory_health_dimensions: {},
    memory_citations_7d: 0,
  },
  activity_heatmap: [],
  weekly_summary: {
    cron_executions: 0,
    conversations: 0,
    messages_sent: 0,
    tool_calls: 0,
    previous_cron_executions: 0,
    previous_conversations: 0,
    previous_messages_sent: 0,
    previous_tool_calls: 0,
  },
  skill_events: [],
  cost_summary: null,
  skill_trends: [],
  skill_health,
});

describe('buildGrowthMarkdown skill ranking', () => {
  it('ranks judged skills by score and leaves out unproven ones, whose score only reflects missing evidence', () => {
    const markdown = buildGrowthMarkdown(
      dashboard([skill('steady', 'HEALTHY', 70), skill('too-new', 'UNPROVEN', 80), skill('star', 'STAR', 100)]),
      labels,
    );

    expect(markdown).toContain('star|100|STAR|6\nsteady|70|HEALTHY|6');
    expect(markdown).not.toContain('too-new');
  });

  it('omits the skill section when no skill has a verdict yet', () => {
    const markdown = buildGrowthMarkdown(dashboard([skill('too-new', 'UNPROVEN', 40)]), labels);

    expect(markdown).not.toContain('Skill health');
  });

  it('does not reorder the dashboard data it was given', () => {
    const items = [skill('low', 'AT_RISK', 20), skill('high', 'STAR', 95)];

    buildGrowthMarkdown(dashboard(items), labels);

    expect(items.map((item) => item.skill_name)).toEqual(['low', 'high']);
  });
});
