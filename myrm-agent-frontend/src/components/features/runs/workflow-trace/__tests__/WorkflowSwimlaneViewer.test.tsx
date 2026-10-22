/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowSwimlaneViewer } from '../WorkflowSwimlaneViewer';
import { WorkflowTraceService } from '../workflowTraceService';
import { WorkflowTraceResponse } from '../workflowTraceTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '多步骤工作流全景执行轨迹',
    subtitle: '5 阶全生命周期链路可视化、节点级全息审计快照与断点自愈重放',
    stageIntake: '需求接入与目标对齐',
    stagePlanning: '任务拓扑拆解规划',
    stageDispatch: '调度流转与沙箱分配',
    stageExecution: '分步执行与实时校验',
    stageClosure: '终态闭环与审计定稿',
    statusCompleted: '已完成',
    statusRunning: '执行中',
    totalTokens: '总 Token 消耗',
    totalDuration: '总耗时',
    replayFromNodeBtn: '从此节点断点重放',
    close: '关闭',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockTrace: WorkflowTraceResponse = {
  workflow_id: 'wf-sec-01',
  task_id: 'task-sec-01',
  title: 'FastAPI 认证与鉴权自动化审计',
  current_stage: 'closure',
  nodes: [
    {
      node_id: 'node-1-intake',
      step_number: 1,
      title: '需求接入与业务目标对齐',
      stage: 'intake',
      status: 'completed',
      input_payload: { repo: 'myrm' },
      output_payload: { goal: 'scan' },
      prompt_excerpt: '接入目标',
      tools_called: ['parse_intent'],
      tokens_consumed: 400,
      validation_scores: {
        completeness: 0.98,
        accuracy: 0.95,
        compliance: 1.0,
        relevance: 0.96,
        composite_score: 0.97,
      },
      duration_ms: 450.0,
      created_at: '2026-10-13T00:00:00Z',
      identity_hash: 'hash-node-1',
    },
    {
      node_id: 'node-2-planning',
      step_number: 2,
      title: '任务拓扑拆解规划',
      stage: 'planning',
      status: 'completed',
      input_payload: { strategy: 'fuzzing' },
      output_payload: { dag: 'pipeline' },
      prompt_excerpt: '规划任务',
      tools_called: ['plan_dag'],
      tokens_consumed: 600,
      validation_scores: {
        completeness: 0.94,
        accuracy: 0.92,
        compliance: 0.99,
        relevance: 0.95,
        composite_score: 0.95,
      },
      duration_ms: 550.0,
      created_at: '2026-10-13T00:00:00Z',
      identity_hash: 'hash-node-2',
    },
  ],
  total_tokens: 1000,
  total_duration_ms: 1000.0,
};

describe('WorkflowSwimlaneViewer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders swimlane viewer with workflow title and KPI metrics', async () => {
    vi.spyOn(WorkflowTraceService, 'getWorkflowTrace').mockResolvedValueOnce(mockTrace);

    render(<WorkflowSwimlaneViewer workflowId="wf-sec-01" />);

    expect(await screen.findByText('FastAPI 认证与鉴权自动化审计')).toBeInTheDocument();
    expect(screen.getByText('1000')).toBeInTheDocument();
    expect(screen.getByText('1000 ms')).toBeInTheDocument();
  });

  it('renders ordered nodes and opens node holographic audit drawer on click', async () => {
    vi.spyOn(WorkflowTraceService, 'getWorkflowTrace').mockResolvedValueOnce(mockTrace);

    render(<WorkflowSwimlaneViewer workflowId="wf-sec-01" />);

    expect(await screen.findByText('需求接入与业务目标对齐')).toBeInTheDocument();
    expect(screen.getAllByText('任务拓扑拆解规划')[0]).toBeInTheDocument();
    expect(screen.getByText('Step #1')).toBeInTheDocument();
    expect(screen.getByText('Step #2')).toBeInTheDocument();

    const nodeButton = screen.getByRole('button', { name: /Step #1/i });
    fireEvent.click(nodeButton);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('hash-node-1')).toBeInTheDocument();
  });

  it('refetches trace when refresh button is clicked', async () => {
    const traceSpy = vi
      .spyOn(WorkflowTraceService, 'getWorkflowTrace')
      .mockResolvedValueOnce(mockTrace)
      .mockResolvedValueOnce(mockTrace);

    render(<WorkflowSwimlaneViewer workflowId="wf-sec-01" />);

    await screen.findByText('FastAPI 认证与鉴权自动化审计');

    const refreshBtn = screen.getByRole('button', { name: 'Refresh workflow trace' });
    await act(async () => {
      fireEvent.click(refreshBtn);
    });

    expect(traceSpy).toHaveBeenCalledTimes(2);
  });
});
