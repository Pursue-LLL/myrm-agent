import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SubagentLiveTranscriptCard } from '../SubagentLiveTranscriptCard';

describe('SubagentLiveTranscriptCard', () => {
  it('renders card header, status badges, task summary, smart approval banner, and transcript timeline', () => {
    render(<SubagentLiveTranscriptCard />);

    // 1. Header & Title
    expect(screen.getByTestId('subagent-live-transcript-card')).toBeInTheDocument();
    expect(
      screen.getByText('子 Agent 实时 Live Transcript 与后台委派账本'),
    ).toBeInTheDocument();
    expect(screen.getByText('Hermes v0.19 对标')).toBeInTheDocument();

    // 2. Status Badges
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('MoA: MAX')).toBeInTheDocument();
    expect(screen.getByText('检查点 #3')).toBeInTheDocument();

    // 3. Task details
    expect(screen.getByText('task-hermes-019')).toBeInTheDocument();
    expect(screen.getByText('code_auditor')).toBeInTheDocument();

    // 4. Smart Approvals Banner
    expect(screen.getByText('🛡️ Smart Approvals 独立命令审核')).toBeInTheDocument();
    expect(screen.getByText(/风险评分: 95%/i)).toBeInTheDocument();
    expect(
      screen.getByText('rm -rf /tmp/build_cache_corrupted && git push --force'),
    ).toBeInTheDocument();

    // 5. Timeline Events
    expect(screen.getByText('实时执行轨迹 (Live Transcript Stream)')).toBeInTheDocument();
    expect(screen.getByText('共 3 个事件')).toBeInTheDocument();
    expect(screen.getByText(/初始化子任务/i)).toBeInTheDocument();
  });

  it('allows user to approve a high-risk command once and logs the approval event', () => {
    render(<SubagentLiveTranscriptCard />);

    const approveBtn = screen.getByText('✅ 单次批准 (Approve Once)');
    fireEvent.click(approveBtn);

    // Approval status updated
    expect(
      screen.getByText(/该命令已单次核准，消费后将自动失效以防越权/i),
    ).toBeInTheDocument();

    // New event added to timeline
    expect(screen.getByText(/用户批准命令/i)).toBeInTheDocument();
    expect(screen.getByText('共 4 个事件')).toBeInTheDocument();
  });

  it('allows user to deny a command with custom /deny reason and triggers self-correction remediation', () => {
    render(<SubagentLiveTranscriptCard />);

    const reasonInput = screen.getByLabelText('Deny reason input');
    fireEvent.change(reasonInput, {
      target: { value: '禁止强推主分支，必须使用 PR 分支合并' },
    });

    const denyBtn = screen.getByText('🛑 拒绝并反馈 (/deny)');
    fireEvent.click(denyBtn);

    // Approval status shows denied and feedback prompt
    expect(
      screen.getByText(/该命令已被用户拒绝。已触发自省闭环/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/禁止强推主分支，必须使用 PR 分支合并/i).length,
    ).toBeGreaterThanOrEqual(1);

    // Event logged
    expect(screen.getByText(/用户拒绝执行命令/i)).toBeInTheDocument();
    expect(screen.getByText('共 4 个事件')).toBeInTheDocument();
  });

  it('simulates next step live emit and increments checkpoint and sequence', () => {
    render(<SubagentLiveTranscriptCard />);

    const nextStepBtn = screen.getByText('➕ 模拟下一步 (Live Emit)');
    fireEvent.click(nextStepBtn);

    // Checkpoint incremented to 4
    expect(screen.getByText('检查点 #4')).toBeInTheDocument();
    expect(screen.getByText('共 4 个事件')).toBeInTheDocument();
    expect(screen.getByText(/深度推理中：核验多 Agent 间无死锁/i)).toBeInTheDocument();
  });

  it('simulates host crash and resumes from persistent ledger checkpoint', () => {
    render(<SubagentLiveTranscriptCard />);

    const crashBtn = screen.getByText('🔄 模拟重启自愈 (Ledger Recover)');
    fireEvent.click(crashBtn);

    // Status changed to PAUSED with recovery message
    expect(screen.getByText('PAUSED')).toBeInTheDocument();
    expect(
      screen.getByText(/宿主意外中断：已从本地持久化账本 \(Ledger\) 恢复检查点/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/\[孤儿任务自愈\] 进程重启后已成功重连持久账本/i)).toBeInTheDocument();
  });
});
