/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MobileHitlApprovalCard } from '../MobileHitlApprovalCard';
import type { HitlApprovalPayload } from '../mobileCockpitTypes';

const mockPayload: HitlApprovalPayload = {
  requestId: 'req-mobile-test-01',
  actionTitle: '删除生产测试沙箱容器',
  commandOrTool: 'docker rm -f sandbox-prod-09',
  scopeDescription: '远程沙箱工作区 (1 个活动实例)',
  riskLevel: 'high',
  rawParams: {
    container_id: 'sandbox-prod-09',
    force: true,
  },
};

describe('MobileHitlApprovalCard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders action details and high risk badge correctly', () => {
    render(
      <MobileHitlApprovalCard
        payload={mockPayload}
        onDecision={vi.fn()}
      />,
    );

    expect(screen.getByText('删除生产测试沙箱容器')).toBeDefined();
    expect(screen.getByText('docker rm -f sandbox-prod-09')).toBeDefined();
    expect(screen.getByText(/高风险|High Risk|riskHigh/i)).toBeDefined();
  });

  it('handles one-tap Approve (Yes) decision', async () => {
    const onDecisionMock = vi.fn().mockResolvedValue(undefined);

    render(
      <MobileHitlApprovalCard
        payload={mockPayload}
        onDecision={onDecisionMock}
      />,
    );

    const approveBtn = screen.getByTestId('hitl-approve-btn');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(onDecisionMock).toHaveBeenCalledWith({
        requestId: 'req-mobile-test-01',
        decision: 'approve',
      });
    });
  });

  it('handles Reject (No) with optional reason input', async () => {
    const onDecisionMock = vi.fn().mockResolvedValue(undefined);

    render(
      <MobileHitlApprovalCard
        payload={mockPayload}
        onDecision={onDecisionMock}
      />,
    );

    const rejectBtn = screen.getByTestId('hitl-reject-btn');
    fireEvent.click(rejectBtn);

    const input = screen.getByPlaceholderText(/拒绝原因|reason/i);
    fireEvent.change(input, { target: { value: '容器内包含未备份的临时代码' } });

    const confirmRejectBtn = screen.getByRole('button', { name: /确认拒绝|rejectConfirm/i });
    fireEvent.click(confirmRejectBtn);

    await waitFor(() => {
      expect(onDecisionMock).toHaveBeenCalledWith({
        requestId: 'req-mobile-test-01',
        decision: 'reject',
        reason: '容器内包含未备份的临时代码',
      });
    });
  });

  it('handles Steer (Intervene) with guidance input', async () => {
    const onDecisionMock = vi.fn().mockResolvedValue(undefined);

    render(
      <MobileHitlApprovalCard
        payload={mockPayload}
        onDecision={onDecisionMock}
      />,
    );

    const steerBtn = screen.getByTestId('hitl-steer-btn');
    fireEvent.click(steerBtn);

    const input = screen.getByPlaceholderText(/修正指令|steerPlaceholder/i);
    fireEvent.change(input, { target: { value: '请先执行 git diff 检查未提交修改' } });

    const submitSteerBtn = screen.getByRole('button', { name: /发送干预|steerSubmit/i });
    fireEvent.click(submitSteerBtn);

    await waitFor(() => {
      expect(onDecisionMock).toHaveBeenCalledWith({
        requestId: 'req-mobile-test-01',
        decision: 'steer',
        steerInstruction: '请先执行 git diff 检查未提交修改',
      });
    });
  });

  it('toggles raw parameter inspector', () => {
    render(
      <MobileHitlApprovalCard
        payload={mockPayload}
        onDecision={vi.fn()}
      />,
    );

    const toggleBtn = screen.getByRole('button', { name: /参数详情/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('container_id:')).toBeDefined();
    expect(screen.getByText('sandbox-prod-09')).toBeDefined();
  });
});
