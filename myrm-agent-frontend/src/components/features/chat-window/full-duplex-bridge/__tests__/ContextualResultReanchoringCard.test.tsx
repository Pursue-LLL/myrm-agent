import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ContextualResultReanchoringCard } from '../ContextualResultReanchoringCard';
import { useFullDuplexBridgeStore } from '../useFullDuplexBridgeStore';
import { ReanchoredResultCard } from '../fullDuplexBridgeTypes';

describe('ContextualResultReanchoringCard', () => {
  const baseCard: ReanchoredResultCard = {
    id: 'res-1',
    workerId: 'w1',
    title: '竞品调研全景报告',
    category: '调研分析',
    elapsedSec: 145,
    isAdopted: false,
    createdAt: Date.now(),
    artifact: {
      id: 'art-1',
      title: 'benchmark_report.pdf',
      type: 'report',
      summary: '梳理了三大前沿 Agent 的全双工交互指标。',
      previewSnippet: 'TTFT < 320ms, Worker 吞吐 +380%',
    },
  };

  beforeEach(() => {
    useFullDuplexBridgeStore.getState().reset();
    useFullDuplexBridgeStore.setState({
      reanchoredResults: [baseCard],
    });
  });

  it('renders card title, category, elapsed time, and summary snippet', () => {
    render(<ContextualResultReanchoringCard card={baseCard} />);

    expect(screen.getByTestId('reanchored-result-res-1')).toBeInTheDocument();
    expect(screen.getByText('竞品调研全景报告')).toBeInTheDocument();
    expect(screen.getByText('后台成果已就绪')).toBeInTheDocument();
    expect(screen.getByText('耗时 2m 25s')).toBeInTheDocument();
    expect(
      screen.getByText('梳理了三大前沿 Agent 的全双工交互指标。'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('TTFT < 320ms, Worker 吞吐 +380%'),
    ).toBeInTheDocument();
    expect(screen.getByText('benchmark_report.pdf')).toBeInTheDocument();
  });

  it('handles clicking view artifact callback', () => {
    const handleView = vi.fn();
    render(
      <ContextualResultReanchoringCard
        card={baseCard}
        onViewArtifact={handleView}
      />,
    );

    const viewBtn = screen.getByRole('button', { name: /预览工件/ });
    act(() => {
      fireEvent.click(viewBtn);
    });

    expect(handleView).toHaveBeenCalledTimes(1);
    expect(handleView).toHaveBeenCalledWith(baseCard);
  });

  it('adopts result and triggers onAdopt callback', () => {
    const handleAdopt = vi.fn();
    const { rerender } = render(
      <ContextualResultReanchoringCard
        card={baseCard}
        onAdopt={handleAdopt}
      />,
    );

    const adoptBtn = screen.getByRole('button', {
      name: /采纳并继续讨论/,
    });
    act(() => {
      fireEvent.click(adoptBtn);
    });

    expect(handleAdopt).toHaveBeenCalledTimes(1);
    expect(handleAdopt).toHaveBeenCalledWith(baseCard);

    // 重新渲染为已采纳状态
    const updatedCard = { ...baseCard, isAdopted: true };
    rerender(
      <ContextualResultReanchoringCard
        card={updatedCard}
        onAdopt={handleAdopt}
      />,
    );

    expect(screen.getByText('已采纳至会话')).toBeInTheDocument();
  });

  it('dismisses card when close button is clicked', () => {
    render(<ContextualResultReanchoringCard card={baseCard} />);

    const closeBtn = screen.getByRole('button', {
      name: '关闭成果通知卡片',
    });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(
      useFullDuplexBridgeStore.getState().reanchoredResults.length,
    ).toBe(0);
  });
});
