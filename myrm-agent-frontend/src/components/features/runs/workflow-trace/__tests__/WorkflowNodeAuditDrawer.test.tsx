/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowNodeAuditDrawer } from '../WorkflowNodeAuditDrawer';
import { WorkflowTraceService } from '../workflowTraceService';
import { WorkflowNodeSnapshot } from '../workflowTraceTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    statusCompleted: '已完成',
    statusRunning: '执行中',
    statusFailed: '失败',
    statusPending: '等待中',
    validationScoreTitle: '四维校验评分',
    compositeScore: '综合评分',
    completeness: '完整性',
    accuracy: '准确性',
    compliance: '合规性',
    relevance: '相关性',
    promptExcerpt: 'Prompt 指令摘要',
    toolsInvoked: '调用工具',
    inputPayload: '输入参数',
    outputPayload: '中间输出产物',
    steerPromptPlaceholder: '输入引导词或修正指令...',
    overrideInputPlaceholder: '输入待覆盖的 JSON 参数...',
    replayFromNodeBtn: '从此节点断点重放',
    replayingBtn: '断点重放中...',
    replaySuccess: '断点重放自愈成功',
    close: '关闭',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockNode: WorkflowNodeSnapshot = {
  node_id: 'node-3-dispatch',
  step_number: 3,
  title: '智能体编排与隔离沙箱调度',
  stage: 'dispatch',
  status: 'completed',
  input_payload: { sandbox_mode: 'strict_volume_mount', concurrency: 2 },
  output_payload: { allocated_worker: 'worker-01', container_ready: true },
  prompt_excerpt: '调度执行引擎与挂载沙箱 Volume。',
  tools_called: ['sandbox_allocate', 'worker_health_check'],
  tokens_consumed: 310,
  validation_scores: {
    completeness: 0.96,
    accuracy: 0.95,
    compliance: 1.0,
    relevance: 0.94,
    composite_score: 0.96,
  },
  duration_ms: 390.0,
  created_at: '2026-10-13T00:00:00Z',
  identity_hash: 'hash-abc-003',
};

describe('WorkflowNodeAuditDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false or node is null', () => {
    const { container: c1 } = render(
      <WorkflowNodeAuditDrawer isOpen={false} node={mockNode} workflowId="wf-01" onClose={vi.fn()} />,
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <WorkflowNodeAuditDrawer isOpen={true} node={null} workflowId="wf-01" onClose={vi.fn()} />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders node snapshot details, 4D scorecard, and tools invoked', () => {
    render(<WorkflowNodeAuditDrawer isOpen={true} node={mockNode} workflowId="wf-01" onClose={vi.fn()} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('智能体编排与隔离沙箱调度')).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('390.0 ms')).toBeInTheDocument();
    expect(screen.getByText('310 tok')).toBeInTheDocument();
    expect(screen.getByText('hash-abc-003')).toBeInTheDocument();

    expect(screen.getByText(/综合评分: 96.0%/)).toBeInTheDocument();
    expect(screen.getByText('96%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();

    expect(screen.getByText('sandbox_allocate')).toBeInTheDocument();
    expect(screen.getByText('worker_health_check')).toBeInTheDocument();
  });

  it('triggers replay from node and displays success indicator on successful replay', async () => {
    const replaySpy = vi.spyOn(WorkflowTraceService, 'replayFromNode').mockResolvedValueOnce({
      workflow_id: 'wf-01',
      replayed_from_node_id: 'node-3-dispatch',
      status: 'completed',
      message: 'Replay success',
      replayed_nodes: [],
    });

    const handleReplaySuccess = vi.fn();

    render(
      <WorkflowNodeAuditDrawer
        isOpen={true}
        node={mockNode}
        workflowId="wf-01"
        onClose={vi.fn()}
        onReplaySuccess={handleReplaySuccess}
      />,
    );

    const steerInput = screen.getByPlaceholderText('输入引导词或修正指令...');
    fireEvent.change(steerInput, { target: { value: '提升并发至 4' } });

    const overrideInput = screen.getByPlaceholderText('输入待覆盖的 JSON 参数...');
    fireEvent.change(overrideInput, { target: { value: '{"concurrency": 4}' } });

    const replayBtn = screen.getByRole('button', { name: /从此节点断点重放/i });
    await act(async () => {
      fireEvent.click(replayBtn);
    });

    expect(replaySpy).toHaveBeenCalledWith({
      workflow_id: 'wf-01',
      node_id: 'node-3-dispatch',
      override_inputs: { concurrency: 4 },
      steer_prompt: '提升并发至 4',
    });

    expect(screen.getByText('断点重放自愈成功')).toBeInTheDocument();
    expect(handleReplaySuccess).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<WorkflowNodeAuditDrawer isOpen={true} node={mockNode} workflowId="wf-01" onClose={handleClose} />);

    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
