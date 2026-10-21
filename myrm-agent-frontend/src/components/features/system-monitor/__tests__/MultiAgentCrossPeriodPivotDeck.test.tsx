import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MultiAgentCrossPeriodPivotDeck } from '../MultiAgentCrossPeriodPivotDeck';
import {
  CrossPeriodPivotReportItem,
  TeamAdoptionInsightsItem,
  UserGamifiedProfileItem,
} from '../crossPeriodMilestoneTypes';

describe('MultiAgentCrossPeriodPivotDeck Component', () => {
  const mockReport: CrossPeriodPivotReportItem = {
    current_period: {
      period_type: 'weekly',
      period_label: '2026-W41',
      start_date: '2026-10-06',
      end_date: '2026-10-12',
      total_tokens: 480000,
      total_cost_usd: 0.4285,
      total_invocations: 38,
      agent_breakdowns: [
        {
          agent_id: 'coding_agent',
          agent_name: 'Coding Specialist',
          tokens_in: 200000,
          tokens_out: 100000,
          total_tokens: 300000,
          token_share_pct: 62.5,
          cost_usd: 0.28,
          invocation_count: 24,
          success_rate: 1.0,
          avg_latency_ms: 1100.0,
        },
        {
          agent_id: 'workbuddy',
          agent_name: 'WorkBuddy Prime',
          tokens_in: 120000,
          tokens_out: 60000,
          total_tokens: 180000,
          token_share_pct: 37.5,
          cost_usd: 0.1485,
          invocation_count: 14,
          success_rate: 0.95,
          avg_latency_ms: 950.0,
        },
      ],
    },
    previous_period: {
      period_type: 'weekly',
      period_label: '2026-W40',
      start_date: '2026-09-29',
      end_date: '2026-10-05',
      total_tokens: 400000,
      total_cost_usd: 0.35,
      total_invocations: 30,
      agent_breakdowns: [],
    },
    token_growth_pct: 20.0,
    cost_growth_pct: 22.4,
    invocation_growth_pct: 26.7,
  };

  const mockProfile: UserGamifiedProfileItem = {
    user_id: 'emp_001',
    user_name: 'Devin Chen',
    level: 3,
    rank_title: 'AI 进阶驾驶员',
    current_xp: 220,
    next_level_xp: 500,
    total_xp: 1420,
    streak_days: 9,
    daily_tasks: [
      {
        id: 'task_code_review',
        title: '委托 Agent 完成一次代码审查',
        description: '在开发或合并前使用 CodingAgent 自动化扫描安全与设计规范',
        xp_reward: 100,
        is_completed: false,
        progress: 0,
        max_progress: 1,
      },
      {
        id: 'task_research_summary',
        title: '委托 Agent 归纳一份行业/技术情报',
        description: '利用 ResearchAgent 快速提取关键洞察与技术要点',
        xp_reward: 80,
        is_completed: true,
        progress: 1,
        max_progress: 1,
      },
    ],
    badges: [
      {
        id: 'badge_first_collab',
        name: '破冰启航',
        description: '完成第一次与数字员工的协同交互',
        tier: 'bronze',
        icon: 'compass',
        is_unlocked: true,
        unlocked_at: '2026-10-01T08:00:00Z',
      },
      {
        id: 'badge_master_commander',
        name: '多智能体大宗师',
        description: '在日常业务中熟练调度 3 种及以上不同专属 Agent',
        tier: 'platinum',
        icon: 'crown',
        is_unlocked: false,
      },
    ],
  };

  const mockTeamInsights: TeamAdoptionInsightsItem = {
    total_active_members: 12,
    average_streak_days: 6.8,
    total_team_sessions: 245,
    top_task_categories: [
      { category: 'code_review', count: '120' },
      { category: 'research', count: '85' },
    ],
    leaderboard: [
      {
        user_id: 'emp_001',
        user_name: 'Devin Chen',
        department: 'Engineering',
        streak_days: 9,
        sessions_count: 58,
        total_tokens: 650000,
        level: 3,
        rank_title: 'AI 进阶驾驶员',
      },
      {
        user_id: 'emp_002',
        user_name: 'Sarah Lin',
        department: 'Product',
        streak_days: 7,
        sessions_count: 42,
        total_tokens: 420000,
        level: 2,
        rank_title: 'AI 协同新手',
      },
    ],
  };

  it('renders correctly with pivot report view, KPI cards, and breakdowns', () => {
    render(
      <MultiAgentCrossPeriodPivotDeck
        report={mockReport}
        profile={mockProfile}
        teamInsights={mockTeamInsights}
      />
    );

    expect(screen.getByTestId('multi-agent-cross-period-pivot-deck')).toBeInTheDocument();
    expect(screen.getAllByText('2026-W41').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('480,000')).toBeInTheDocument();
    expect(screen.getByText('$0.4285')).toBeInTheDocument();
    expect(screen.getByText('Coding Specialist')).toBeInTheDocument();
    expect(screen.getByText('WorkBuddy Prime')).toBeInTheDocument();
    expect(screen.getByText('62.5%')).toBeInTheDocument();
    expect(screen.getByText('37.5%')).toBeInTheDocument();
  });

  it('handles period selection and refresh triggers', async () => {
    const handlePeriodChange = vi.fn();
    const handleRefresh = vi.fn();

    render(
      <MultiAgentCrossPeriodPivotDeck
        report={mockReport}
        profile={mockProfile}
        teamInsights={mockTeamInsights}
        onPeriodChange={handlePeriodChange}
        onRefresh={handleRefresh}
      />
    );

    const monthlyPill = screen.getByTestId('period-pill-monthly');
    await act(async () => {
      fireEvent.click(monthlyPill);
    });
    expect(handlePeriodChange).toHaveBeenCalledWith('monthly');

    const refreshBtn = screen.getByTestId('btn-refresh-pivot');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(handleRefresh).toHaveBeenCalled();
  });

  it('switches to gamification tab and handles daily task claim', async () => {
    const handleClaimTask = vi.fn().mockResolvedValue(undefined);

    render(
      <MultiAgentCrossPeriodPivotDeck
        report={mockReport}
        profile={mockProfile}
        teamInsights={mockTeamInsights}
        onClaimTask={handleClaimTask}
      />
    );

    // Click Gamification Tab
    const tabGamification = screen.getByTestId('tab-gamification');
    await act(async () => {
      fireEvent.click(tabGamification);
    });

    expect(screen.getAllByText(/AI 进阶驾驶员/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/220 \/ 500 XP/)).toBeInTheDocument();
    expect(screen.getByText('委托 Agent 完成一次代码审查')).toBeInTheDocument();
    expect(screen.getByText('破冰启航')).toBeInTheDocument();
    expect(screen.getByText('多智能体大宗师')).toBeInTheDocument();

    // Claim daily task
    const claimBtn = screen.getByTestId('claim-task-task_code_review');
    await act(async () => {
      fireEvent.click(claimBtn);
    });
    expect(handleClaimTask).toHaveBeenCalledWith('task_code_review');
  });

  it('switches to team leaderboard tab and displays rankings', async () => {
    render(
      <MultiAgentCrossPeriodPivotDeck
        report={mockReport}
        profile={mockProfile}
        teamInsights={mockTeamInsights}
      />
    );

    const tabTeam = screen.getByTestId('tab-team');
    await act(async () => {
      fireEvent.click(tabTeam);
    });

    expect(screen.getByText('12 人')).toBeInTheDocument();
    expect(screen.getByText('6.8 天')).toBeInTheDocument();
    expect(screen.getByText('245 次')).toBeInTheDocument();
    expect(screen.getAllByText('Devin Chen').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Sarah Lin')).toBeInTheDocument();
  });
});
