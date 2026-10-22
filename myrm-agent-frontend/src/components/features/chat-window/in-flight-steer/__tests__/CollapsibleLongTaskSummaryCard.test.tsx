import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CollapsibleLongTaskSummaryCard } from '../CollapsibleLongTaskSummaryCard';
import { useInFlightSteerStore } from '../useInFlightSteerStore';
import type { CollapsibleLongTaskSummary } from '../inFlightSteerTypes';

describe('CollapsibleLongTaskSummaryCard', () => {
  const mockSummary: CollapsibleLongTaskSummary = {
    id: 'summary-test-1',
    chatId: 'chat-test-100',
    goalTitle: 'Cloudflare Migration Workflow',
    totalSteps: 4,
    completedSteps: 2,
    currentActiveAgentName: 'DevOps Specialist',
    keyFindings: [
      'Identified 12 edge worker endpoints',
      'Configured D1 SQLite persistence schema',
    ],
    isCollapsed: true,
    updatedAt: Date.now(),
  };

  beforeEach(() => {
    useInFlightSteerStore.getState().clearSwimlanes();
    useInFlightSteerStore.getState().setTaskSummary(mockSummary);
  });

  it('renders goal title, step count, progress percentage, and current active agent', () => {
    render(<CollapsibleLongTaskSummaryCard summary={mockSummary} />);

    expect(screen.getByText('Cloudflare Migration Workflow')).toBeInTheDocument();
    expect(screen.getByText(/2\/4 步骤 \(50%\)/)).toBeInTheDocument();
    expect(screen.getByText(/当前负责: DevOps Specialist/)).toBeInTheDocument();
    expect(screen.getByText('展开详情')).toBeInTheDocument();

    // Collapsed initially, findings not rendered
    expect(screen.queryByText('Identified 12 edge worker endpoints')).not.toBeInTheDocument();
  });

  it('toggles collapse state and shows key findings when expanded', () => {
    const { rerender } = render(<CollapsibleLongTaskSummaryCard summary={mockSummary} />);

    const toggleBtn = screen.getByRole('button', { expanded: false });
    fireEvent.click(toggleBtn);

    // Store state updated
    const updatedSummary = useInFlightSteerStore.getState().taskSummaries['summary-test-1'];
    expect(updatedSummary.isCollapsed).toBe(false);

    rerender(<CollapsibleLongTaskSummaryCard summary={updatedSummary} />);

    expect(screen.getByText('折叠摘要')).toBeInTheDocument();
    expect(screen.getByText(/阶段性产物与关键发现 \(2\)/)).toBeInTheDocument();
    expect(screen.getByText('Identified 12 edge worker endpoints')).toBeInTheDocument();
    expect(screen.getByText('Configured D1 SQLite persistence schema')).toBeInTheDocument();
  });

  it('renders fallback text when key findings array is empty in expanded mode', () => {
    const emptyFindingsSummary: CollapsibleLongTaskSummary = {
      ...mockSummary,
      id: 'summary-empty',
      keyFindings: [],
      isCollapsed: false,
    };
    useInFlightSteerStore.getState().setTaskSummary(emptyFindingsSummary);

    render(<CollapsibleLongTaskSummaryCard summary={emptyFindingsSummary} />);

    expect(screen.getByText('暂无阶段性总结产物...')).toBeInTheDocument();
  });
});
