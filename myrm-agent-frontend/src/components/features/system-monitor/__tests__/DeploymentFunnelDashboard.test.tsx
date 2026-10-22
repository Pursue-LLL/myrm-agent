import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DeploymentFunnelDashboard } from '../DeploymentFunnelDashboard';
import type { DeploymentFunnelSnapshot } from '../deploymentFunnelTypes';

describe('DeploymentFunnelDashboard', () => {
  const mockHealthySnapshot: DeploymentFunnelSnapshot = {
    deployment_id: 'dep_healthy_101',
    total_visitors: 100,
    stages: [
      {
        stage: 'STAGE_1_VIEW',
        user_count: 100,
        conversion_rate_pct: 100.0,
        dropoff_rate_pct: 0.0,
      },
      {
        stage: 'STAGE_2_ENGAGE',
        user_count: 85,
        conversion_rate_pct: 85.0,
        dropoff_rate_pct: 15.0,
      },
      {
        stage: 'STAGE_3_ACTION',
        user_count: 70,
        conversion_rate_pct: 70.0,
        dropoff_rate_pct: 17.6,
      },
      {
        stage: 'STAGE_4_COMPLETE',
        user_count: 65,
        conversion_rate_pct: 65.0,
        dropoff_rate_pct: 7.1,
      },
    ],
    dropoff_hotspot_stage: null,
    feedback_counts: {
      POSITIVE: 12,
      NEUTRAL: 3,
      NEGATIVE: 0,
    },
    nudge_required: false,
    nudge_reason: null,
    autonomous_goal_recommendation: null,
    evaluated_at: '2026-10-12T10:00:00Z',
  };

  const mockDropoffSnapshot: DeploymentFunnelSnapshot = {
    deployment_id: 'dep_friction_202',
    total_visitors: 50,
    stages: [
      {
        stage: 'STAGE_1_VIEW',
        user_count: 50,
        conversion_rate_pct: 100.0,
        dropoff_rate_pct: 0.0,
      },
      {
        stage: 'STAGE_2_ENGAGE',
        user_count: 15,
        conversion_rate_pct: 30.0,
        dropoff_rate_pct: 70.0,
      },
      {
        stage: 'STAGE_3_ACTION',
        user_count: 5,
        conversion_rate_pct: 10.0,
        dropoff_rate_pct: 66.7,
      },
      {
        stage: 'STAGE_4_COMPLETE',
        user_count: 2,
        conversion_rate_pct: 4.0,
        dropoff_rate_pct: 60.0,
      },
    ],
    dropoff_hotspot_stage: 'STAGE_2_ENGAGE',
    feedback_counts: {
      POSITIVE: 1,
      NEUTRAL: 2,
      NEGATIVE: 6,
    },
    nudge_required: true,
    nudge_reason: '阶段 [STAGE_2_ENGAGE] 出现显著流失断点 (70.0% 流失率) | 收到 6 条负面用户反馈。',
    autonomous_goal_recommendation: '请以【改善部署物在 STAGE_2_ENGAGE 环节的转化率与用户体验】为高阶目标，自主分析交互瓶颈并提出优化方案。',
    evaluated_at: '2026-10-12T11:00:00Z',
  };

  it('renders healthy deployment funnel with 4 stages and positive sentiment', () => {
    const onRefresh = vi.fn();
    render(<DeploymentFunnelDashboard snapshot={mockHealthySnapshot} onRefresh={onRefresh} />);

    expect(screen.getByText('交付部署漏斗监测与反馈闭环')).toBeInTheDocument();
    expect(screen.getByText('dep_healthy_101')).toBeInTheDocument();
    expect(screen.getAllByText('100').length).toBeGreaterThanOrEqual(1); // total_visitors and stage 1 count

    // 4 阶梯卡片
    expect(screen.getByText('1. 曝光浏览')).toBeInTheDocument();
    expect(screen.getByText('2. 深度交互')).toBeInTheDocument();
    expect(screen.getByText('3. 核心操作')).toBeInTheDocument();
    expect(screen.getByText('4. 达成留存')).toBeInTheDocument();

    // 健康状态下无 Nudge 告警
    expect(screen.getByText('漏斗运行健康，无需推动')).toBeInTheDocument();
    expect(screen.queryByText('流失热点')).not.toBeInTheDocument();

    // 刷新按钮
    const refreshBtn = screen.getByText('刷新数据');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders dropoff hotspot warning, feedback breakdown, and autonomous goal nudge banner', () => {
    render(<DeploymentFunnelDashboard snapshot={mockDropoffSnapshot} />);

    expect(screen.getByText('dep_friction_202')).toBeInTheDocument();

    // 流失热点标签
    expect(screen.getByText('流失热点')).toBeInTheDocument();
    expect(screen.getByText('70.0%')).toBeInTheDocument();

    // 负面反馈高亮
    expect(screen.getByText('6 条')).toBeInTheDocument();

    // Nudge 告警原因与推荐目标
    expect(screen.getByText('自主 Nudge 推动警报')).toBeInTheDocument();
    expect(screen.getByText(/收到 6 条负面用户反馈/)).toBeInTheDocument();
    expect(screen.getByText(/改善部署物在 STAGE_2_ENGAGE 环节的转化率/)).toBeInTheDocument();
  });

  it('dispatches autonomous goal when user clicks dispatch button', async () => {
    const onDispatch = vi.fn().mockResolvedValue(undefined);
    render(
      <DeploymentFunnelDashboard
        snapshot={mockDropoffSnapshot}
        onDispatchAutonomousGoal={onDispatch}
      />
    );

    const dispatchBtn = screen.getByRole('button', { name: '一键派发优化目标' });
    expect(dispatchBtn).toBeInTheDocument();

    fireEvent.click(dispatchBtn);
    expect(onDispatch).toHaveBeenCalledTimes(1);
    expect(onDispatch).toHaveBeenCalledWith(mockDropoffSnapshot.autonomous_goal_recommendation);

    await waitFor(() => {
      expect(
        screen.getByText('✓ 高阶自愈目标已成功派发至自治 Agent 任务队列！')
      ).toBeInTheDocument();
    });
  });
});
