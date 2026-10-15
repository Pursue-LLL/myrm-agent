import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TurnLineageFilterBar } from '../TurnLineageFilterBar';
import { useTurnLineageStore } from '../useTurnLineageStore';
import { TurnAuditRecord } from '../turnLineageTypes';

const mockTurns: TurnAuditRecord[] = [
  {
    id: 'turn-1',
    turnNumber: 1,
    author: 'Developer',
    content: '用户发送需求',
    provenance: {
      originType: 'user_prompt',
      timestamp: '10:00:00',
    },
  },
  {
    id: 'turn-2',
    turnNumber: 2,
    author: 'Planner',
    content: 'Agent 移交规划',
    provenance: {
      originType: 'subagent_delegation',
      timestamp: '10:01:00',
      causalityParentId: 'turn-1',
    },
  },
  {
    id: 'turn-3',
    turnNumber: 3,
    author: 'Daemon',
    content: '定时巡检',
    provenance: {
      originType: 'cron_job',
      timestamp: '10:05:00',
    },
  },
];

describe('TurnLineageFilterBar 组件单测', () => {
  beforeEach(() => {
    useTurnLineageStore.setState({
      turns: mockTurns,
      activeTurnId: null,
      highlightedLineageChain: [],
      filterMode: 'all',
      isRailExpanded: false,
    });
  });

  it('渲染筛选工具栏基本元素与初始轮次统计', () => {
    render(<TurnLineageFilterBar />);

    expect(screen.getByTestId('turn-lineage-filter-bar')).toBeInTheDocument();
    expect(screen.getByText('全部轮次')).toBeInTheDocument();
    expect(screen.getByText('仅人工指令')).toBeInTheDocument();
    expect(screen.getByText('定时自动化')).toBeInTheDocument();
    expect(screen.getByText('Agent 移交')).toBeInTheDocument();
    expect(screen.getByText(/显示/)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('点击筛选按钮切换 filterMode 并正确更新过滤轮次数量', () => {
    render(<TurnLineageFilterBar />);

    const userOnlyBtn = screen.getByText('仅人工指令');
    fireEvent.click(userOnlyBtn);
    expect(useTurnLineageStore.getState().filterMode).toBe('user_only');

    const automatedBtn = screen.getByText('定时自动化');
    fireEvent.click(automatedBtn);
    expect(useTurnLineageStore.getState().filterMode).toBe('automated_only');

    const handoffBtn = screen.getByText('Agent 移交');
    fireEvent.click(handoffBtn);
    expect(useTurnLineageStore.getState().filterMode).toBe('handoff_only');

    const allBtn = screen.getByText('全部轮次');
    fireEvent.click(allBtn);
    expect(useTurnLineageStore.getState().filterMode).toBe('all');
  });

  it('点击时间轴折叠/展开按钮切换 isRailExpanded 状态', () => {
    render(<TurnLineageFilterBar />);

    const toggleBtn = screen.getByRole('button', { name: '展开时间轴' });
    expect(useTurnLineageStore.getState().isRailExpanded).toBe(false);

    fireEvent.click(toggleBtn);
    expect(useTurnLineageStore.getState().isRailExpanded).toBe(true);

    const closeBtn = screen.getByRole('button', { name: '收起时间轴' });
    fireEvent.click(closeBtn);
    expect(useTurnLineageStore.getState().isRailExpanded).toBe(false);
  });
});
