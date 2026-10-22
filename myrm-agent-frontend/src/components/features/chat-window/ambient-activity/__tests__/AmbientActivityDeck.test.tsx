import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { AmbientActivityDeck } from '../AmbientActivityDeck';
import { useAmbientActivityStore } from '../useAmbientActivityStore';

describe('AmbientActivityDeck', () => {
  beforeEach(() => {
    useAmbientActivityStore.getState().reset();
  });

  it('renders nothing when there are no activities', () => {
    const { container } = render(<AmbientActivityDeck />);
    expect(container.firstChild).toBeNull();
  });

  it('renders deck and overview statistics when activities exist', () => {
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 'sess-deck-1',
      sourceAgent: 'CodeArchitect',
      targetAgent: 'Reviewer',
      actionSummary: '推送架构草案',
      payloadSnippet: '{"diff": "+code"}',
      tokenCost: 120,
      latencyMs: 45,
      status: 'completed',
    });

    render(<AmbientActivityDeck />);

    expect(screen.getByTestId('ambient-activity-deck')).toBeDefined();
    expect(screen.getByText('环境态协同活动流')).toBeDefined();
    expect(screen.getByText(/2 个智能体后台协同中/)).toBeDefined();
    expect(screen.getByText(/共完成 1 次微通信/)).toBeDefined();
    expect(screen.getByText(/累计消耗 120 Tokens/)).toBeDefined();
    expect(
      screen.getByText(
        '[@CodeArchitect -> @Reviewer] 推送架构草案 (45ms)',
      ),
    ).toBeDefined();
  });

  it('toggles collapse state when chevron button is clicked', () => {
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 'sess-deck-2',
      sourceAgent: 'BotA',
      targetAgent: 'BotB',
      actionSummary: '数据交换',
      payloadSnippet: '',
      tokenCost: 10,
      latencyMs: 5,
      status: 'completed',
    });

    render(<AmbientActivityDeck />);
    const collapseBtn = screen.getByLabelText('折叠活动流');
    expect(collapseBtn).toBeDefined();

    fireEvent.click(collapseBtn);
    expect(
      useAmbientActivityStore.getState().isDeckCollapsed,
    ).toBe(true);
    expect(
      screen.queryByText('[@BotA -> @BotB] 数据交换 (5ms)'),
    ).toBeNull();
  });

  it('opens inspection drawer when audit button is clicked', () => {
    useAmbientActivityStore.getState().recordActivity({
      sessionId: 'sess-deck-3',
      sourceAgent: 'BotX',
      targetAgent: 'BotY',
      actionSummary: '分析日志',
      payloadSnippet: '',
      tokenCost: 30,
      latencyMs: 12,
      status: 'completed',
    });

    render(<AmbientActivityDeck />);
    const auditBtn = screen.getByText('穿透审计');
    fireEvent.click(auditBtn);

    expect(
      useAmbientActivityStore.getState().isInspectionDrawerOpen,
    ).toBe(true);
  });

  it('selects activity and opens drawer when an activity item row is clicked', () => {
    const actId = useAmbientActivityStore.getState().recordActivity({
      sessionId: 'sess-deck-4',
      sourceAgent: 'Worker1',
      targetAgent: 'Worker2',
      actionSummary: '分块汇总',
      payloadSnippet: '',
      tokenCost: 40,
      latencyMs: 20,
      status: 'completed',
    });

    render(<AmbientActivityDeck />);
    const row = screen.getByText('[@Worker1 -> @Worker2] 分块汇总 (20ms)');
    fireEvent.click(row);

    expect(
      useAmbientActivityStore.getState().isInspectionDrawerOpen,
    ).toBe(true);
    expect(
      useAmbientActivityStore.getState().selectedActivityId,
    ).toBe(actId);
  });
});
