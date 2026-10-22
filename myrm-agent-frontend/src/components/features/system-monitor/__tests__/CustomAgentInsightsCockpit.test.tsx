import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CustomAgentInsightsCockpit } from '../CustomAgentInsightsCockpit';
import type { CustomAgentInsightsData } from '../customAgentInsightsTypes';

describe('CustomAgentInsightsCockpit', () => {
  const mockInsightsData: CustomAgentInsightsData = {
    agent_id: 'architect_agent_01',
    time_window_days: 7,
    total_interactions: 120,
    total_tokens_consumed: 350000,
    intent_clusters: [
      {
        intent_category: 'sql_performance_tuning',
        sample_utterance: 'Optimize slow queries on orders_v2 table',
        request_count: 65,
        share_pct: 54.2,
      },
      {
        intent_category: 'architecture_adr_review',
        sample_utterance: 'Review ADR proposal for dual-write cache pattern',
        request_count: 35,
        share_pct: 29.2,
      },
    ],
    skill_funnel: [
      {
        skill_name: 'sql_explain_analyzer',
        total_calls: 80,
        success_rate_pct: 97.5,
        avg_latency_ms: 125.4,
        p95_latency_ms: 280.0,
        top_error_reasons: ['ExplainTimeout'],
      },
      {
        skill_name: 'git_worktree_manager',
        total_calls: 40,
        success_rate_pct: 100.0,
        avg_latency_ms: 45.2,
        p95_latency_ms: 88.0,
        top_error_reasons: [],
      },
    ],
    hitl_metrics: {
      total_tasks: 25,
      hitl_intercepted_tasks: 2,
      hitl_interception_rate_pct: 8.0,
      avg_approval_wait_seconds: 35.5,
      token_roi_ratio: 3.45,
    },
    generated_at_ms: 1710000000000,
  };

  it('renders header, 4 KPI cards, intent clusters, and skill funnels', () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();

    render(
      <CustomAgentInsightsCockpit
        data={mockInsightsData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    // 头部信息
    expect(screen.getByText('自定义智能体运营洞察驾驶舱')).toBeInTheDocument();
    expect(screen.getByText('Agent ID: architect_agent_01')).toBeInTheDocument();
    expect(screen.getByText('近 7 天统计')).toBeInTheDocument();

    // 4 大 KPI 卡片
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('350,000')).toBeInTheDocument();
    expect(screen.getByText('8.0%')).toBeInTheDocument();
    expect(screen.getByText('高度自主 (High Autonomy)')).toBeInTheDocument();
    expect(screen.getByText('3.45')).toBeInTheDocument();

    // 视角 1: 意图聚类
    expect(screen.getByText('sql_performance_tuning')).toBeInTheDocument();
    expect(screen.getByText('(65 次)')).toBeInTheDocument();
    expect(screen.getByText('54.2%')).toBeInTheDocument();
    expect(
      screen.getByText(/Optimize slow queries on orders_v2 table/)
    ).toBeInTheDocument();

    // 视角 2: 技能健康漏斗
    expect(screen.getByText('sql_explain_analyzer')).toBeInTheDocument();
    expect(screen.getByText('97.5%')).toBeInTheDocument();
    expect(screen.getByText('125.4 ms')).toBeInTheDocument();
    expect(screen.getByText('ExplainTimeout')).toBeInTheDocument();
    expect(screen.getByText('git_worktree_manager')).toBeInTheDocument();
    expect(screen.getByText('无故障')).toBeInTheDocument();

    // 视角 3: 人机协同卡点
    expect(screen.getByText(/35.5 秒/)).toBeInTheDocument();
    expect(screen.getByText(/3.45 份\/万Token/)).toBeInTheDocument();
  });

  it('triggers onRefresh and onReset callbacks', async () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn().mockResolvedValue(undefined);

    render(
      <CustomAgentInsightsCockpit
        data={mockInsightsData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    const refreshBtn = screen.getByRole('button', { name: '刷新洞察' });
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    const resetBtn = screen.getByRole('button', { name: '清空遥测' });
    await React.act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('renders empty states gracefully when no clusters or skills exist', () => {
    const emptyData: CustomAgentInsightsData = {
      ...mockInsightsData,
      total_interactions: 0,
      total_tokens_consumed: 0,
      intent_clusters: [],
      skill_funnel: [],
      hitl_metrics: {
        total_tasks: 0,
        hitl_intercepted_tasks: 0,
        hitl_interception_rate_pct: 0.0,
        avg_approval_wait_seconds: 0.0,
        token_roi_ratio: 1.0,
      },
    };

    render(<CustomAgentInsightsCockpit data={emptyData} />);

    expect(screen.getByText('暂无意图聚类记录')).toBeInTheDocument();
    expect(screen.getByText('暂无技能执行记录')).toBeInTheDocument();
  });
});
