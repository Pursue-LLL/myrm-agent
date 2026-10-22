import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgentDoctorWizard } from '../AgentDoctorWizard';
import { AgentDiagnosticCapsule } from '../AgentDiagnosticCapsule';
import type { TriageReport } from '../types';

describe('AgentDoctorWizard & AgentDiagnosticCapsule', () => {
  const mockHardFailureReport: TriageReport = {
    triage_id: 'triage-fail-001',
    trace_id: 'trace-xyz-100',
    symptom: 'tool_execution_failed',
    root_stage: 'tool_execution',
    negative_outcome: 'none',
    is_system_failure: true,
    summary: '工具沙箱命令执行失败：Docker 容器退出码非 0',
    detailed_reasons: [
      '容器内执行 bash 返回 137 (OOM)',
      '沙箱内存配额限制为 512MB',
    ],
    remediation_action: '调高沙箱运行内存至 1024MB 并清理宿主未释放进程',
    can_redispatch: true,
    created_at: 1700000000,
  };

  const mockNegativeOutcomeReport: TriageReport = {
    triage_id: 'triage-safe-002',
    trace_id: 'trace-xyz-200',
    symptom: 'human_rejection',
    root_stage: 'approval_gate',
    negative_outcome: 'denied',
    is_system_failure: false,
    summary: '高危命令 rm -rf 被审批人拒绝执行',
    detailed_reasons: ['用户在人机协同卡片中明确点击了拒绝执行'],
    remediation_action: '按安全策略优雅终止，提示用户修改为安全命令',
    can_redispatch: false,
    created_at: 1700000000,
  };

  it('renders AgentDoctorWizard with hard failure and executes redispatch', async () => {
    const handleClose = vi.fn();
    const handleRedispatch = vi.fn().mockResolvedValue(undefined);

    render(
      <AgentDoctorWizard
        report={mockHardFailureReport}
        isOpen={true}
        onClose={handleClose}
        onRedispatch={handleRedispatch}
      />
    );

    // 标题与 ID
    expect(screen.getByText(/智能体故障诊断与分诊向导/i)).toBeInTheDocument();
    expect(screen.getByText(/triage-fail-001/i)).toBeInTheDocument();
    expect(screen.getByText(/系统硬故障/i)).toBeInTheDocument();

    // 链路断点流水渲染（可能与底部 select option 选项重复，采用 getAllByText）
    expect(screen.getAllByText('用户输入摄入').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('工具执行沙箱').length).toBeGreaterThanOrEqual(1);

    // 诊断原因
    expect(screen.getByText(/容器内执行 bash 返回 137/i)).toBeInTheDocument();
    expect(screen.getByText(/调高沙箱运行内存至 1024MB/i)).toBeInTheDocument();

    // 触发重发
    const redispatchBtn = screen.getByRole('button', { name: /就地恢复并重发/i });
    expect(redispatchBtn).not.toBeDisabled();
    fireEvent.click(redispatchBtn);

    await waitFor(() => {
      expect(handleRedispatch).toHaveBeenCalledWith(
        'triage-fail-001',
        'trace-xyz-100',
        'tool_execution'
      );
    });

    // 触发关闭
    const closeBtn = screen.getByRole('button', { name: /关闭向导/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('renders AgentDoctorWizard with negative outcome correctly', () => {
    render(
      <AgentDoctorWizard
        report={mockNegativeOutcomeReport}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText(/业务负例\/预期防御/i)).toBeInTheDocument();
    expect(screen.getByText(/安全防御拦截/i)).toBeInTheDocument();
    expect(screen.getByText(/人工审批拒绝/i)).toBeInTheDocument();

    // 无法重发
    const redispatchBtn = screen.getByRole('button', { name: /就地恢复并重发/i });
    expect(redispatchBtn).toBeDisabled();
  });

  it('renders AgentDiagnosticCapsule and triggers open callback', () => {
    const handleOpenDoctor = vi.fn();
    const { rerender } = render(
      <AgentDiagnosticCapsule report={null} onOpenDoctor={handleOpenDoctor} />
    );

    // report 为 null 时不渲染
    expect(screen.queryByRole('button', { name: /查看智能体排障向导/i })).toBeNull();

    // report 存在时渲染胶囊并响应点击
    rerender(
      <AgentDiagnosticCapsule
        report={mockHardFailureReport}
        onOpenDoctor={handleOpenDoctor}
      />
    );

    const capsuleBtn = screen.getByRole('button', { name: /查看智能体排障向导/i });
    expect(capsuleBtn).toBeInTheDocument();
    expect(screen.getByText(/沙箱崩溃/i)).toBeInTheDocument();

    fireEvent.click(capsuleBtn);
    expect(handleOpenDoctor).toHaveBeenCalledTimes(1);
  });
});
