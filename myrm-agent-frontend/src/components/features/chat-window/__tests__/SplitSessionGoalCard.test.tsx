'use client';

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  SplitSessionGoalCard,
  SplitSessionGoalData,
} from '../SplitSessionGoalCard';

const mockGoalData: SplitSessionGoalData = {
  goalId: 'ssg-7788',
  templateId: 'ship-then-plan-v1',
  templateName: '双窗口交付与规划模板',
  phase: 'ship_in_progress',
  shipSessionId: 'sess-ship-01',
  testPassRatePct: 100,
  automatedTestsPassed: true,
  deliverables: [
    {
      id: 'd-1',
      title: 'feat: add device mesh scheduler and api',
      type: 'code_diff',
      verified: true,
    },
    {
      id: 'd-2',
      title: 'pytest report: 4/4 passed',
      type: 'test_report',
      verified: true,
    },
  ],
  contextTokensSaved: 32400,
  weeklyQuotaSavedPct: 18,
  nextPlanDraft: {
    title: '分布式集群分片自愈规划',
    summary: '梳理异构节点故障转移与数据复制心跳协议',
    targetObjectives: ['容灾策略制定', '心跳延迟削峰'],
    suggestedTemplateId: 'ship-then-plan-v1',
  },
};

describe('SplitSessionGoalCard', () => {
  it('renders card header, phase badge, and template meta', () => {
    render(<SplitSessionGoalCard goal={mockGoalData} />);

    expect(screen.getByTestId('split-session-goal-card')).toBeInTheDocument();
    expect(screen.getByText('双窗口交付与规划模板')).toBeInTheDocument();
    expect(screen.getByText('ship-then-plan-v1')).toBeInTheDocument();
    expect(screen.getByText('ssg-7788')).toBeInTheDocument();
    expect(screen.getByTestId('phase-badge')).toHaveTextContent('Window 1: 交付实施中');
  });

  it('renders dual-window stepper with Window 1 active', () => {
    render(<SplitSessionGoalCard goal={mockGoalData} />);

    expect(screen.getByText('Window 1: Ship (交付)')).toBeInTheDocument();
    expect(screen.getByText('Window 2: Plan (规划)')).toBeInTheDocument();
  });

  it('renders automated test verification gate and session badge', () => {
    render(<SplitSessionGoalCard goal={mockGoalData} />);

    expect(screen.getByText('100% 测试通过')).toBeInTheDocument();
    expect(screen.getByText('(100% 达成)')).toBeInTheDocument();
    expect(screen.getByText(/会话: sess-ship-01/)).toBeInTheDocument();
  });

  it('renders deliverables dossier with verified status badges', () => {
    render(<SplitSessionGoalCard goal={mockGoalData} />);

    expect(screen.getByTestId('deliverables-list')).toBeInTheDocument();
    expect(screen.getByText('feat: add device mesh scheduler and api')).toBeInTheDocument();
    expect(screen.getByText('pytest report: 4/4 passed')).toBeInTheDocument();
    expect(screen.getAllByText('已核验')).toHaveLength(2);
  });

  it('renders context reset savings and token economy banner', () => {
    render(<SplitSessionGoalCard goal={mockGoalData} />);

    const banner = screen.getByTestId('token-economy-banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent('32,400');
    expect(banner).toHaveTextContent('周配额预计节省 18%');
  });

  it('renders next plan draft and triggers drafting next goal callback', async () => {
    const handleDraftNextGoal = vi.fn().mockResolvedValue(undefined);
    render(
      <SplitSessionGoalCard
        goal={mockGoalData}
        onDraftNextGoal={handleDraftNextGoal}
      />
    );

    expect(screen.getByTestId('next-plan-draft-card')).toBeInTheDocument();
    expect(screen.getByText(/下一迭代规划草案: 分布式集群分片自愈规划/)).toBeInTheDocument();
    expect(screen.getByText('• 容灾策略制定')).toBeInTheDocument();
    expect(screen.getByText('• 心跳延迟削峰')).toBeInTheDocument();

    const publishBtn = screen.getByTestId('publish-draft-button');
    await act(async () => {
      fireEvent.click(publishBtn);
    });
    expect(handleDraftNextGoal).toHaveBeenCalledWith('ssg-7788', mockGoalData.nextPlanDraft);
  });

  it('triggers onAdvanceStage when clicking advance button', async () => {
    const handleAdvance = vi.fn().mockResolvedValue(undefined);
    render(
      <SplitSessionGoalCard
        goal={mockGoalData}
        onAdvanceStage={handleAdvance}
      />
    );

    const advanceBtn = screen.getByTestId('advance-stage-button');
    expect(advanceBtn).toHaveTextContent('推进至: Window 1: 交付已核验');

    await act(async () => {
      fireEvent.click(advanceBtn);
    });
    expect(handleAdvance).toHaveBeenCalledWith('ssg-7788', 'ship_verified');
  });

  it('triggers onAbandon when clicking abandon button', async () => {
    const handleAbandon = vi.fn().mockResolvedValue(undefined);
    render(
      <SplitSessionGoalCard
        goal={mockGoalData}
        onAbandon={handleAbandon}
      />
    );

    const abandonBtn = screen.getByTestId('abandon-goal-button');
    expect(abandonBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(abandonBtn);
    });
    expect(handleAbandon).toHaveBeenCalledWith('ssg-7788');
  });

  it('renders completed state properly and hides abandon button', () => {
    const completedGoal: SplitSessionGoalData = {
      ...mockGoalData,
      phase: 'completed',
    };

    render(<SplitSessionGoalCard goal={completedGoal} />);

    expect(screen.getByTestId('phase-badge')).toHaveTextContent('已完成双阶段流转');
    expect(screen.queryByTestId('advance-stage-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('abandon-goal-button')).not.toBeInTheDocument();
  });
});
