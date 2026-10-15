import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentGranularCostRow } from '../AgentGranularCostRow';
import { useAgentGranularCostStore } from '../useAgentGranularCostStore';

describe('AgentGranularCostRow', () => {
  beforeEach(() => {
    useAgentGranularCostStore.getState().reset();
  });

  const mockProfile = {
    agentId: 'agent-planner',
    agentName: '架构规划专家 (Planner)',
    role: '系统顶层解构与分步任务编排',
    avatarIconName: 'BrainCircuit',
    promptTokens: 42500,
    completionTokens: 8200,
    cachedTokens: 12000,
    totalTokens: 50700,
    estimatedCostUsd: 0.082,
    costRate: { prompt: 0.0015, completion: 0.002 },
    historyPoints: [
      { timestamp: 1, tokens: 12000, cost: 0.018 },
      { timestamp: 2, tokens: 18500, cost: 0.031 },
    ],
  };

  it('renders agent name, role, total token badge, and estimated cost', () => {
    render(<AgentGranularCostRow profile={mockProfile} />);

    expect(screen.getByText('架构规划专家 (Planner)')).toBeInTheDocument();
    expect(screen.getByText('系统顶层解构与分步任务编排')).toBeInTheDocument();
    expect(screen.getByText('50.7k')).toBeInTheDocument();
    expect(screen.getByText('$0.082')).toBeInTheDocument();
  });

  it('reveals granular cost breakdown popover on mouse enter and hides on mouse leave', () => {
    render(<AgentGranularCostRow profile={mockProfile} />);

    const rowContainer = screen.getByText('架构规划专家 (Planner)').closest('div[role="presentation"]');
    expect(rowContainer).toBeInTheDocument();

    // 默认不展示详细浮层
    expect(screen.queryByText('算力消耗与成本透视')).not.toBeInTheDocument();

    // 鼠标移入
    if (rowContainer) {
      fireEvent.mouseEnter(rowContainer);
    }

    expect(screen.getByText('算力消耗与成本透视')).toBeInTheDocument();
    expect(screen.getByText('42,500')).toBeInTheDocument(); // prompt tokens
    expect(screen.getByText('8,200')).toBeInTheDocument();  // completion tokens
    expect(screen.getByText('12,000')).toBeInTheDocument(); // cached tokens

    // 鼠标移出
    if (rowContainer) {
      fireEvent.mouseLeave(rowContainer);
    }

    expect(screen.queryByText('算力消耗与成本透视')).not.toBeInTheDocument();
  });
});
