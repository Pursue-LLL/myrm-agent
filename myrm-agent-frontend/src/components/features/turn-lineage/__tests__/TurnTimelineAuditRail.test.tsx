import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TurnTimelineAuditRail } from '../TurnTimelineAuditRail';
import { useTurnLineageStore } from '../useTurnLineageStore';
import type { ChatTurnItem } from '../turnLineageTypes';
import { asChatTurn, type TurnFixture } from './turnFixtures';

const mockTimelineTurns: ChatTurnItem[] = ([
  {
    id: 'turn-root',
    turnNumber: 1,
    author: 'User',
    content: '开始执行系统构架任务',
    provenance: {
      originType: 'user_direct',
      timestamp: '14:00:00',
    },
  },
  {
    id: 'turn-agent-1',
    turnNumber: 2,
    author: 'ArchitectAgent',
    content: '拆分微前端沙箱与执行引擎',
    provenance: {
      originType: 'subagent_delegation',
      timestamp: '14:01:20',
      causalityParentId: 'turn-root',
    },
  },
  {
    id: 'turn-cron',
    turnNumber: 3,
    author: 'Watchdog',
    content: '心跳健康巡检完成',
    provenance: {
      originType: 'cron_job',
      timestamp: '14:05:00',
    },
  },
] satisfies TurnFixture[]).map(asChatTurn);

describe('TurnTimelineAuditRail 组件单测', () => {
  beforeEach(() => {
    useTurnLineageStore.setState({
      turns: mockTimelineTurns,
      activeTurnId: null,
      highlightedLineageChain: [],
      filterMode: 'all',
      isRailExpanded: true,
    });
  });

  it('当 isRailExpanded 为 false 时不渲染任何节点', () => {
    useTurnLineageStore.setState({ isRailExpanded: false });
    const { container } = render(<TurnTimelineAuditRail />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('turn-timeline-audit-rail')).not.toBeInTheDocument();
  });

  it('当 isRailExpanded 为 true 时完整渲染时序因果时间轴与节点', () => {
    render(<TurnTimelineAuditRail />);

    expect(screen.getByTestId('turn-timeline-audit-rail')).toBeInTheDocument();
    expect(screen.getByText('时序因果时间轴')).toBeInTheDocument();
    expect(screen.getByText('3 节点')).toBeInTheDocument();
    expect(screen.getByText(/开始执行系统构架任务/)).toBeInTheDocument();
    expect(screen.getByText(/拆分微前端沙箱与执行引擎/)).toBeInTheDocument();
    expect(screen.getByText(/心跳健康巡检完成/)).toBeInTheDocument();
  });

  it('点击某一轮次节点能选中并高亮溯源因果链', () => {
    render(<TurnTimelineAuditRail />);

    const agentTurnBtn = screen.getByText(/拆分微前端沙箱与执行引擎/).closest('button');
    expect(agentTurnBtn).not.toBeNull();
    if (agentTurnBtn) {
      fireEvent.click(agentTurnBtn);
    }

    const state = useTurnLineageStore.getState();
    expect(state.activeTurnId).toBe('turn-agent-1');
    expect(state.highlightedLineageChain).toEqual(['turn-root', 'turn-agent-1']);
    expect(screen.getByText(/因果链: turn-root → turn-agent-1/)).toBeInTheDocument();
  });

  it('在过滤模式下仅显示匹配的因果节点', () => {
    useTurnLineageStore.setState({ filterMode: 'automated_only' });
    render(<TurnTimelineAuditRail />);

    expect(screen.getByText('1 节点')).toBeInTheDocument();
    expect(screen.queryByText(/开始执行系统构架任务/)).not.toBeInTheDocument();
    expect(screen.getByText(/心跳健康巡检完成/)).toBeInTheDocument();
  });
});
