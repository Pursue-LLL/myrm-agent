'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  AgentHandoffCard,
  AgentParticipant,
  HandoffStageItem,
} from '../AgentHandoffCard';

const mockSourceAgent: AgentParticipant = {
  profileId: 'atlas-orchestrator',
  name: 'Atlas Orchestrator',
  avatar: '/avatars/atlas.png',
  role: 'Team Lead & Coordinator',
};

const mockTargetAgent: AgentParticipant = {
  profileId: 'gilfoyle-sec',
  name: 'Gilfoyle Security',
  avatar: '/avatars/gilfoyle.png',
  role: 'Security Specialist',
  personalityTags: ['cynical', 'skeptical', 'strict'],
};

const mockStages: HandoffStageItem[] = [
  {
    stageId: 'intent_routing',
    label: '意图确认与分流',
    status: 'completed',
    summary: '意图已明确派发',
  },
  {
    stageId: 'context_injection',
    label: '环境与上下文准备',
    status: 'completed',
    summary: '沙箱凭据与代码已挂载',
  },
  {
    stageId: 'action_execution',
    label: '动作执行与计算',
    status: 'in_progress',
    summary: '正在执行渗透扫描脚本...',
  },
  {
    stageId: 'artifact_delivery',
    label: '工件生成与交付',
    status: 'pending',
  },
  {
    stageId: 'acceptance_verification',
    label: '验收评测与确认',
    status: 'pending',
  },
];

describe('AgentHandoffCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders participant personas, intent, and five stages properly', () => {
    render(
      <AgentHandoffCard
        handoffId="handoff_101"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Audit OAuth PKCE token exchange against RFC 7636"
        status="in_progress"
        stages={mockStages}
        resumeContextNote="Resumed from Sprint-12 Auth session"
      />
    );

    expect(screen.getByTestId('agent-handoff-card')).toBeInTheDocument();
    expect(screen.getByText('Atlas Orchestrator')).toBeInTheDocument();
    expect(screen.getByText('Gilfoyle Security')).toBeInTheDocument();
    expect(screen.getByText('Security Specialist')).toBeInTheDocument();
    expect(screen.getByText('cynical')).toBeInTheDocument();
    expect(screen.getByText('skeptical')).toBeInTheDocument();
    expect(screen.getByText('strict')).toBeInTheDocument();
    expect(
      screen.getByText('Audit OAuth PKCE token exchange against RFC 7636')
    ).toBeInTheDocument();

    // Resume context badge
    expect(screen.getByTestId('resume-context-badge')).toBeInTheDocument();
    expect(screen.getByText('恢复上下文')).toBeInTheDocument();

    // Five-stage stack
    expect(screen.getByTestId('five-stages-container')).toBeInTheDocument();
    expect(screen.getByText('2/5 完成')).toBeInTheDocument();
    expect(screen.getByTestId('stage-item-intent_routing')).toBeInTheDocument();
    expect(screen.getByTestId('stage-item-action_execution')).toBeInTheDocument();
  });

  it('renders awaiting approval gate and handles onApprove callback', async () => {
    const onApproveMock = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentHandoffCard
        handoffId="handoff_102"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Run automated database schema migration"
        status="awaiting_approval"
        requiresApproval={true}
        stages={mockStages}
        onApprove={onApproveMock}
      />
    );

    expect(screen.getByTestId('awaiting-approval-badge')).toBeInTheDocument();
    expect(screen.getByTestId('approval-actions-container')).toBeInTheDocument();
    expect(screen.getByText('批准派发')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('approve-button'));
    await waitFor(() => {
      expect(onApproveMock).toHaveBeenCalledWith('handoff_102');
    });
  });

  it('renders awaiting approval gate and handles onReject callback', async () => {
    const onRejectMock = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentHandoffCard
        handoffId="handoff_102_rej"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Dangerous drop database migration"
        status="awaiting_approval"
        requiresApproval={true}
        stages={mockStages}
        onReject={onRejectMock}
      />
    );

    expect(screen.getByText('驳回移交')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('reject-button'));
    await waitFor(() => {
      expect(onRejectMock).toHaveBeenCalledWith('handoff_102_rej');
    });
  });

  it('renders completion state with deliverables and handles onSendToPR CTA', async () => {
    const onSendToPRMock = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentHandoffCard
        handoffId="handoff_103"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Generate security compliance report"
        status="completed"
        stages={mockStages.map((s) => ({ ...s, status: 'completed' }))}
        deliverables={['audit_report.json', 'commit: #8fa1c3']}
        onSendToPR={onSendToPRMock}
      />
    );

    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('任务已交付完成')).toBeInTheDocument();
    expect(screen.getByText('audit_report.json')).toBeInTheDocument();
    expect(screen.getByText('commit: #8fa1c3')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('send-to-pr-button'));
    await waitFor(() => {
      expect(onSendToPRMock).toHaveBeenCalledWith('handoff_103');
    });
  });

  it('renders completion state and handles onAccept CTA', async () => {
    const onAcceptMock = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentHandoffCard
        handoffId="handoff_103_acc"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Accept verified output"
        status="completed"
        stages={mockStages.map((s) => ({ ...s, status: 'completed' }))}
        deliverables={['final_report.pdf']}
        onAccept={onAcceptMock}
      />
    );

    fireEvent.click(screen.getByTestId('accept-deliverable-button'));
    await waitFor(() => {
      expect(onAcceptMock).toHaveBeenCalledWith('handoff_103_acc');
    });
  });

  it('renders orchestrator unified review summary and supports toggle collapse', () => {
    render(
      <AgentHandoffCard
        handoffId="handoff_104"
        sourceAgent={mockSourceAgent}
        targetAgent={mockTargetAgent}
        taskIntent="Analyze system architecture"
        status="completed"
        stages={mockStages}
        orchestratorSummary="Orchestrator Atlas verified all security checklist items. Ready for production rollout."
      />
    );

    expect(
      screen.getByText(
        'Orchestrator Atlas verified all security checklist items. Ready for production rollout.'
      )
    ).toBeInTheDocument();

    const toggleButton = screen.getByTestId('toggle-summary-button');
    // Collapse summary
    fireEvent.click(toggleButton);
    expect(
      screen.queryByTestId('orchestrator-summary-content')
    ).not.toBeInTheDocument();

    // Re-expand summary
    fireEvent.click(toggleButton);
    expect(
      screen.getByTestId('orchestrator-summary-content')
    ).toBeInTheDocument();
  });
});
