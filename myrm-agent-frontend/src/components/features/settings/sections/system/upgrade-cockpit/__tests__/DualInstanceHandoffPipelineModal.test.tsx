import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DualInstanceHandoffPipelineModal } from '../DualInstanceHandoffPipelineModal';
import type { UpgradeStageStep } from '../upgradeCockpitTypes';

const mockSteps: UpgradeStageStep[] = [
  {
    stage: 'snapshot_diff',
    title: '差分快照备份',
    description: '快照已固化',
    status: 'completed',
    progressPercent: 100,
  },
  {
    stage: 'source_pull',
    title: '源码热拉取',
    description: '增量补丁下载',
    status: 'running',
    progressPercent: 60,
  },
  {
    stage: 'dependency_heal',
    title: '依赖自愈同步',
    description: '等待就绪',
    status: 'pending',
  },
];

describe('DualInstanceHandoffPipelineModal', () => {
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <DualInstanceHandoffPipelineModal
        isOpen={false}
        currentStage="idle"
        steps={mockSteps}
        onClose={vi.fn()}
        onRollback={vi.fn()}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders dual instance handoff cards and pipeline steps when isOpen is true', () => {
    render(
      <DualInstanceHandoffPipelineModal
        isOpen={true}
        currentStage="source_pull"
        steps={mockSteps}
        onClose={vi.fn()}
        onRollback={vi.fn()}
      />,
    );

    expect(screen.getByTestId('dual-instance-upgrade-modal')).toBeInTheDocument();
    expect(screen.getByText('双实例无感升级流水线')).toBeInTheDocument();
    expect(screen.getByText(/旧实例/)).toBeInTheDocument();
    expect(screen.getByText(/新实例/)).toBeInTheDocument();
    expect(screen.getByText('差分快照备份')).toBeInTheDocument();
    expect(screen.getByText('源码热拉取')).toBeInTheDocument();
    expect(screen.getByText('执行中...')).toBeInTheDocument();
  });

  it('renders complete banner on complete stage and enables rollback button', () => {
    const onRollback = vi.fn();
    const onClose = vi.fn();

    render(
      <DualInstanceHandoffPipelineModal
        isOpen={true}
        currentStage="complete"
        steps={mockSteps}
        onClose={onClose}
        onRollback={onRollback}
      />,
    );

    expect(screen.getByTestId('upgrade-complete-banner')).toBeInTheDocument();
    expect(screen.getByText('升级完成！新实例已原子接替服务')).toBeInTheDocument();

    const rollbackBtn = screen.getByTestId('rollback-trigger-btn');
    expect(rollbackBtn).not.toBeDisabled();
    fireEvent.click(rollbackBtn);
    expect(onRollback).toHaveBeenCalled();

    // Confirm finish button
    const finishBtn = screen.getByTestId('confirm-finish-btn');
    expect(finishBtn).toHaveTextContent('体验新版本');
    fireEvent.click(finishBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it('renders rollback banner when currentStage is rolled_back', () => {
    render(
      <DualInstanceHandoffPipelineModal
        isOpen={true}
        currentStage="rolled_back"
        steps={mockSteps}
        onClose={vi.fn()}
        onRollback={vi.fn()}
      />,
    );

    expect(screen.getByTestId('upgrade-rollback-banner')).toBeInTheDocument();
    expect(screen.getByText('已原子回滚至上一稳定版本快照')).toBeInTheDocument();
  });
});
