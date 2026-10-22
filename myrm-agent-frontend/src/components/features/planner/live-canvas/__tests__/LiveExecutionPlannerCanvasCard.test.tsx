import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { LiveExecutionPlannerCanvasCard } from '../LiveExecutionPlannerCanvasCard';
import { usePlannerCanvasStore } from '../usePlannerCanvasStore';

describe('LiveExecutionPlannerCanvasCard', () => {
  beforeEach(() => {
    usePlannerCanvasStore.getState().resetToMockPlanner();
    vi.restoreAllMocks();
  });

  it('正确渲染顶层卡片、任务进度徽标与运行中步骤横幅', () => {
    render(<LiveExecutionPlannerCanvasCard />);

    expect(
      screen.getByTestId('live-execution-planner-canvas-card')
    ).toBeInTheDocument();
    expect(screen.getByTestId('planner-progress-badge')).toHaveTextContent(
      '进度 2/5'
    );
    expect(screen.getByTestId('running-node-banner')).toHaveTextContent(
      '正在执行第 3 步：生成前端 UI 交互组件'
    );
  });

  it('正确渲染 DAG 画布与沙箱预览视窗并响应节点点击', () => {
    render(<LiveExecutionPlannerCanvasCard />);

    expect(screen.getByTestId('planner-dag-graph-view')).toBeInTheDocument();
    expect(screen.getByTestId('sandbox-live-preview-view')).toBeInTheDocument();

    const node1 = screen.getByTestId('planner-node-step-1-analysis');
    fireEvent.click(node1);

    expect(usePlannerCanvasStore.getState().selectedNodeId).toBe(
      'step-1-analysis'
    );
    expect(screen.getByTestId('selected-node-details')).toHaveTextContent(
      '意图拆解与依赖分析'
    );
  });

  it('支持切换视口模式并在沙箱视窗中正确应用', () => {
    render(<LiveExecutionPlannerCanvasCard />);

    const mobileBtn = screen.getByTestId('viewport-btn-mobile');
    fireEvent.click(mobileBtn);

    expect(usePlannerCanvasStore.getState().viewportMode).toBe('mobile');
  });

  it('支持切换主视图排版模式（分屏 / 仅画布 / 仅沙箱）', () => {
    render(<LiveExecutionPlannerCanvasCard />);

    const plannerOnlyBtn = screen.getByTestId('viewmode-btn-planner');
    fireEvent.click(plannerOnlyBtn);

    expect(usePlannerCanvasStore.getState().viewMode).toBe('planner-only');
    expect(screen.getByTestId('planner-dag-graph-view')).toBeInTheDocument();
    expect(
      screen.queryByTestId('sandbox-live-preview-view')
    ).not.toBeInTheDocument();

    const sandboxOnlyBtn = screen.getByTestId('viewmode-btn-sandbox');
    fireEvent.click(sandboxOnlyBtn);

    expect(usePlannerCanvasStore.getState().viewMode).toBe('sandbox-only');
    expect(screen.getByTestId('sandbox-live-preview-view')).toBeInTheDocument();
    expect(
      screen.queryByTestId('planner-dag-graph-view')
    ).not.toBeInTheDocument();
  });

  it('点击重置按钮能够还原规划状态', () => {
    render(<LiveExecutionPlannerCanvasCard />);

    act(() => {
      usePlannerCanvasStore.getState().setViewMode('sandbox-only');
    });

    const resetBtn = screen.getByTestId('reset-planner-btn');
    fireEvent.click(resetBtn);

    expect(usePlannerCanvasStore.getState().viewMode).toBe('split');
  });
});
