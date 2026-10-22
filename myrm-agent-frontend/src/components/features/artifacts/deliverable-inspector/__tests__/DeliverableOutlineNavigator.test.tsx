import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliverableOutlineNavigator } from '../DeliverableOutlineNavigator';
import type { DeliverableNode } from '../deliverableInspectorTypes';

describe('DeliverableOutlineNavigator', () => {
  const mockNodes: DeliverableNode[] = [
    {
      id: 'slide-1',
      index: 1,
      title: '首页封面',
      summary: '项目启动会汇报',
      nodeType: 'slide',
      content: '# 首页封面',
    },
    {
      id: 'slide-2',
      index: 2,
      title: '数据大盘',
      summary: 'Q3 营收增长 200%',
      nodeType: 'slide',
      content: '## 数据大盘',
      metadata: { lastPatchedAt: 1757000000000 },
    },
    {
      id: 'slide-3',
      index: 3,
      title: '未来规划',
      summary: '后续阶段里程碑',
      nodeType: 'slide',
      content: '## 未来规划',
    },
  ];

  it('renders outline navigation with node count and type header', () => {
    render(
      <DeliverableOutlineNavigator
        nodes={mockNodes}
        activeNodeId="slide-1"
        onSelectNode={vi.fn()}
        deliverableType="slides"
      />,
    );

    expect(screen.getByText('幻灯片单页大纲')).toBeDefined();
    expect(screen.getByText('3 节点')).toBeDefined();
    expect(screen.getByText('首页封面')).toBeDefined();
    expect(screen.getByText('数据大盘')).toBeDefined();
  });

  it('triggers onSelectNode callback when clicking a node item', () => {
    const onSelectNode = vi.fn();
    render(
      <DeliverableOutlineNavigator
        nodes={mockNodes}
        activeNodeId="slide-1"
        onSelectNode={onSelectNode}
        deliverableType="slides"
      />,
    );

    const targetNodeBtn = screen.getByText('数据大盘');
    fireEvent.click(targetNodeBtn);

    expect(onSelectNode).toHaveBeenCalledWith('slide-2');
  });

  it('filters nodes based on search input', () => {
    render(
      <DeliverableOutlineNavigator
        nodes={mockNodes}
        activeNodeId="slide-1"
        onSelectNode={vi.fn()}
        deliverableType="slides"
      />,
    );

    const searchInput = screen.getByPlaceholderText('搜索节点或序号...');
    fireEvent.change(searchInput, { target: { value: '营收' } });

    expect(screen.getByText('数据大盘')).toBeDefined();
    expect(screen.queryByText('首页封面')).toBeNull();
    expect(screen.queryByText('未来规划')).toBeNull();
  });

  it('renders patched badge for modified nodes', () => {
    render(
      <DeliverableOutlineNavigator
        nodes={mockNodes}
        activeNodeId="slide-1"
        onSelectNode={vi.fn()}
        deliverableType="slides"
      />,
    );

    expect(screen.getByText('已修')).toBeDefined();
  });
});
