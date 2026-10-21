import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RetrievalDecisionTreeView } from '../RetrievalDecisionTreeView';
import { RetrievalTraceDrawer } from '../RetrievalTraceDrawer';
import type { VisitedPathTrace, RetrievalTreeNode } from '../types';

describe('RetrievalDecisionTreeView & RetrievalTraceDrawer', () => {
  const mockNodes: RetrievalTreeNode[] = [
    {
      node_id: 'root-system',
      name: '系统核心架构',
      path: '/knowledge/architecture',
      depth: 0,
      similarity_score: 0.86,
      pruning_threshold: 0.75,
      is_pruned: false,
      pruning_reason: 'none',
      reason_detail: '',
      is_hit: false,
      metadata: { category: 'arch' },
      children: [
        {
          node_id: 'sub-observe',
          name: '可观测性设计规范',
          path: '/knowledge/architecture/observability',
          depth: 1,
          similarity_score: 0.92,
          pruning_threshold: 0.75,
          is_pruned: false,
          pruning_reason: 'none',
          reason_detail: '',
          is_hit: false,
          metadata: {},
          children: [
            {
              node_id: 'leaf-trace-doc',
              name: 'retrieval_trace.md',
              path: '/knowledge/architecture/observability/trace.md',
              depth: 2,
              similarity_score: 0.96,
              pruning_threshold: 0.75,
              is_pruned: false,
              pruning_reason: 'none',
              reason_detail: '',
              is_hit: true,
              metadata: {},
              children: [],
            },
            {
              node_id: 'leaf-legacy-doc',
              name: 'legacy_metrics.md',
              path: '/knowledge/architecture/observability/legacy.md',
              depth: 2,
              similarity_score: 0.71,
              pruning_threshold: 0.75,
              is_pruned: true,
              pruning_reason: 'score_below_threshold',
              reason_detail: '相关度 0.710 低于剪枝阈值 0.750',
              is_hit: false,
              metadata: {},
              children: [],
            },
          ],
        },
      ],
    },
    {
      node_id: 'root-legal',
      name: '法务合规分类',
      path: '/knowledge/legal',
      depth: 0,
      similarity_score: 0.42,
      pruning_threshold: 0.75,
      is_pruned: true,
      pruning_reason: 'score_below_threshold',
      reason_detail: '相关度 0.420 低于剪枝阈值 0.750',
      is_hit: false,
      metadata: {},
      children: [],
    },
  ];

  const mockTrace: VisitedPathTrace = {
    trace_id: 'trace-viking-demo-100',
    query: 'OpenViking 分层记忆检索可观察性',
    root_nodes: mockNodes,
    total_nodes_visited: 4,
    pruned_nodes_count: 2,
    hits_count: 1,
    duration_ms: 45.6,
    created_at: 1700000000,
  };

  it('renders empty fallback when no nodes provided', () => {
    render(<RetrievalDecisionTreeView nodes={[]} />);
    expect(screen.getByText('暂无检索下钻决策树记录')).toBeInTheDocument();
  });

  it('renders tree nodes with hits, pruning badges and details', () => {
    render(<RetrievalDecisionTreeView nodes={mockNodes} defaultExpanded={true} />);

    // 根节点
    expect(screen.getByText('系统核心架构')).toBeInTheDocument();
    expect(screen.getByText('法务合规分类')).toBeInTheDocument();

    // 叶子命中装配节点
    expect(screen.getByText('retrieval_trace.md')).toBeInTheDocument();
    expect(screen.getByText('命中装配')).toBeInTheDocument();

    // 叶子剪枝节点与原因
    expect(screen.getByText('legacy_metrics.md')).toBeInTheDocument();
    expect(screen.getAllByText('分值低于阈值').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/相关度 0.710 低于剪枝阈值/i)).toBeInTheDocument();

    // 折叠/展开测试
    const toggleButtons = screen.getAllByRole('button', { name: /折叠子目录/i });
    expect(toggleButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(toggleButtons[0]);
    // 再次点击展开
    fireEvent.click(toggleButtons[0]);
  });

  it('renders RetrievalTraceDrawer and triggers simulation callback with sliders', async () => {
    const handleClose = vi.fn();
    const handleSimulate = vi.fn().mockResolvedValue(undefined);

    render(
      <RetrievalTraceDrawer
        trace={mockTrace}
        isOpen={true}
        onClose={handleClose}
        onSimulate={handleSimulate}
      />
    );

    // 抽屉头部与指标
    expect(screen.getByText(/上下文检索决策树与剪枝留痕/i)).toBeInTheDocument();
    expect(screen.getByText(/trace-viking-demo-100/i)).toBeInTheDocument();
    expect(screen.getByText(/45.6 ms/i)).toBeInTheDocument();
    expect(screen.getByText('4 个')).toBeInTheDocument();
    expect(screen.getByText('2 个')).toBeInTheDocument();
    expect(screen.getByText('1 个')).toBeInTheDocument();

    // 实验场滑块调节与重新模拟
    const thresholdSlider = screen.getByLabelText('剪枝阈值调节');
    fireEvent.change(thresholdSlider, { target: { value: '0.80' } });

    const topKSlider = screen.getByLabelText('Top-K 数量调节');
    fireEvent.change(topKSlider, { target: { value: '5' } });

    const simulateBtn = screen.getByRole('button', { name: /实验场模拟重算/i });
    expect(simulateBtn).not.toBeDisabled();
    fireEvent.click(simulateBtn);

    await waitFor(() => {
      expect(handleSimulate).toHaveBeenCalledWith(0.8, 5);
    });

    // 关闭抽屉
    const closeBtn = screen.getByRole('button', { name: /关闭抽屉/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
