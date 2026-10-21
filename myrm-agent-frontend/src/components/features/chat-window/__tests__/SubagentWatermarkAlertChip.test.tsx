import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SubagentWatermarkAlertChip } from '../SubagentWatermarkAlertChip';

describe('SubagentWatermarkAlertChip', () => {
  it('renders null when turn count is strictly below the 80% threshold', () => {
    // 199 / 250 = 79.6% (< 80%)
    render(
      <SubagentWatermarkAlertChip
        subagentId="sub-alpha"
        subagentName="AlphaScout"
        currentTurn={199}
        maxTurns={250}
      />,
    );

    expect(screen.queryByTestId('subagent-watermark-alert')).not.toBeInTheDocument();
  });

  it('renders alert chip with warning header, progress bar, and remaining turns when reaching 80%', () => {
    // 200 / 250 = 80.0%
    render(
      <SubagentWatermarkAlertChip
        subagentId="sub-beta"
        subagentName="BetaWorker"
        currentTurn={200}
        maxTurns={250}
      />,
    );

    expect(screen.getByTestId('subagent-watermark-alert')).toBeInTheDocument();
    expect(screen.getByText('[80% 配额水位预警]')).toBeInTheDocument();
    expect(screen.getByText('BetaWorker')).toBeInTheDocument();
    expect(screen.getByText('80.0%')).toBeInTheDocument();
    expect(screen.getByText('已执行 200 / 250 轮')).toBeInTheDocument();
    expect(screen.getByText('剩余 50 轮达到上限')).toBeInTheDocument();
    expect(screen.getByTestId('watermark-progress-bar')).toBeInTheDocument();
  });

  it('calls onExpandBudget callback and disables button when clicked', () => {
    const handleExpand = vi.fn();
    render(
      <SubagentWatermarkAlertChip
        subagentId="sub-gamma"
        subagentName="GammaCoder"
        currentTurn={210}
        maxTurns={250}
        onExpandBudget={handleExpand}
      />,
    );

    const expandBtn = screen.getByTestId('expand-budget-button');
    expect(expandBtn).toHaveTextContent('扩容 +100 轮');
    fireEvent.click(expandBtn);

    expect(handleExpand).toHaveBeenCalledTimes(1);
    expect(handleExpand).toHaveBeenCalledWith('sub-gamma');
    expect(expandBtn).toHaveTextContent('已扩容配额');
    expect(expandBtn).toBeDisabled();
  });

  it('calls onNotifyParent callback with task details and disables button when clicked', () => {
    const handleNotify = vi.fn();
    render(
      <SubagentWatermarkAlertChip
        subagentId="sub-delta"
        subagentName="DeltaTester"
        currentTurn={225}
        maxTurns={250}
        onNotifyParent={handleNotify}
      />,
    );

    const notifyBtn = screen.getByTestId('notify-parent-button');
    expect(notifyBtn).toHaveTextContent('通知父智能体');
    fireEvent.click(notifyBtn);

    expect(handleNotify).toHaveBeenCalledTimes(1);
    expect(handleNotify).toHaveBeenCalledWith('sub-delta', 225, 250);
    expect(notifyBtn).toHaveTextContent('已通知父智能体');
    expect(notifyBtn).toBeDisabled();
  });

  it('calls onDismiss and dismisses alert chip when clicking close button', () => {
    const handleDismiss = vi.fn();
    render(
      <SubagentWatermarkAlertChip
        subagentId="sub-epsilon"
        subagentName="EpsilonReviewer"
        currentTurn={202}
        maxTurns={250}
        onDismiss={handleDismiss}
      />,
    );

    expect(screen.getByTestId('subagent-watermark-alert')).toBeInTheDocument();
    const dismissBtn = screen.getByTestId('dismiss-alert-button');
    fireEvent.click(dismissBtn);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
    expect(handleDismiss).toHaveBeenCalledWith('sub-epsilon');
    expect(screen.queryByTestId('subagent-watermark-alert')).not.toBeInTheDocument();
  });
});
