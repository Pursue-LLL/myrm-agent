import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { TerminalFreeFinalCard } from '../TerminalFreeFinalCard';
import { assembleFinalCardContract } from '../finalCardEngine';
import { useFinalCardStore } from '../useFinalCardStore';

describe('TerminalFreeFinalCard', () => {
  beforeEach(() => {
    act(() => {
      useFinalCardStore.getState().resetStore();
    });
  });

  it('renders card title, summary, duration, and tokens', () => {
    const contract = assembleFinalCardContract({
      turnId: 'turn-1',
      title: '架构重构完成',
      summary: '成功将 5 个模块迁移到 TypeScript Strict',
      status: 'completed',
      executionDurationMs: 4200,
      tokensUsed: { prompt: 500, completion: 1500, total: 2000 },
    });

    render(<TerminalFreeFinalCard contract={contract} />);

    expect(screen.getByText('架构重构完成')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('成功将 5 个模块迁移到 TypeScript Strict')).toBeInTheDocument();
    expect(screen.getByText('4.2s')).toBeInTheDocument();
    expect(screen.getByText('2,000 tokens')).toBeInTheDocument();
  });

  it('renders different statuses properly', () => {
    const failedContract = assembleFinalCardContract({
      turnId: 'turn-fail',
      title: '执行失败',
      summary: '编译出错',
      status: 'failed',
    });

    const { rerender } = render(<TerminalFreeFinalCard contract={failedContract} />);
    expect(screen.getByText('失败')).toBeInTheDocument();

    const actionReqContract = assembleFinalCardContract({
      turnId: 'turn-action',
      title: '等待确认',
      summary: '需人工审核',
      status: 'requires_action',
    });
    rerender(<TerminalFreeFinalCard contract={actionReqContract} />);
    expect(screen.getByText('待确认')).toBeInTheDocument();

    const partialContract = assembleFinalCardContract({
      turnId: 'turn-partial',
      title: '部分成功',
      summary: '主线通过，单测存在跳过',
      status: 'partial_success',
    });
    rerender(<TerminalFreeFinalCard contract={partialContract} />);
    expect(screen.getByText('部分完成')).toBeInTheDocument();
  });

  it('renders key decisions and artifacts with clicks', () => {
    const onArtifactClick = vi.fn();
    const contract = assembleFinalCardContract({
      turnId: 'turn-2',
      title: '产物与决策',
      summary: '交付详情',
      keyDecisions: ['决定消除 any 类型', '收敛单文件行数至 300 行内'],
      artifacts: [
        { id: 'art-code', name: 'app.tsx', type: 'code', path: '/src/app.tsx', sizeBytes: 2048, previewable: true },
        { id: 'art-diff', name: 'patch.diff', type: 'diff', path: '/patch.diff', sizeBytes: 512, previewable: false },
      ],
    });

    render(
      <TerminalFreeFinalCard
        contract={contract}
        onArtifactClick={onArtifactClick}
      />,
    );

    expect(screen.getByText('决定消除 any 类型')).toBeInTheDocument();
    expect(screen.getByText('收敛单文件行数至 300 行内')).toBeInTheDocument();

    const codeArtBtn = screen.getByText('app.tsx');
    fireEvent.click(codeArtBtn);
    expect(onArtifactClick).toHaveBeenCalledWith(contract.artifacts[0]);
  });

  it('renders action options and handles user interactions', () => {
    const onActionClick = vi.fn();
    const contract = assembleFinalCardContract({
      turnId: 'turn-3',
      title: '下一步行动',
      summary: '请选择后续流程',
      actionOptions: [
        { id: 'opt-run', label: '运行集成测试', actionKind: 'run_tests', isPrimary: true },
        { id: 'opt-commit', label: '直接提交', actionKind: 'commit_code' },
      ],
    });

    render(
      <TerminalFreeFinalCard
        contract={contract}
        onActionClick={onActionClick}
      />,
    );

    const runBtn = screen.getByText('运行集成测试');
    fireEvent.click(runBtn);
    expect(onActionClick).toHaveBeenCalledWith(contract.actionOptions[0]);

    const commitBtn = screen.getByText('直接提交');
    fireEvent.click(commitBtn);
    expect(onActionClick).toHaveBeenCalledWith(contract.actionOptions[1]);
  });

  it('triggers onViewTranscript callback or opens store modal', () => {
    const contract = assembleFinalCardContract({
      turnId: 'turn-4',
      title: '轨迹卡片',
      summary: '查看执行日志',
      rawLogsPreview: ['log1', 'log2'],
    });

    const onViewTranscript = vi.fn();

    // 1. With onViewTranscript prop
    const { rerender } = render(
      <TerminalFreeFinalCard
        contract={contract}
        onViewTranscript={onViewTranscript}
      />,
    );

    const viewBtn = screen.getByText(/调阅执行轨迹/);
    fireEvent.click(viewBtn);
    expect(onViewTranscript).toHaveBeenCalledTimes(1);

    // 2. Without onViewTranscript prop -> updates store activeTranscriptCardId
    rerender(<TerminalFreeFinalCard contract={contract} />);
    fireEvent.click(viewBtn);
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBe(contract.id);
  });
});
