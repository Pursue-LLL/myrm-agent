import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InteractiveCalloutWorkspaceCard } from '../InteractiveCalloutWorkspaceCard';
import { useCalloutAnchorStore } from '../useCalloutAnchorStore';

class MockResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;

describe('InteractiveCalloutWorkspaceCard', () => {
  beforeEach(() => {
    useCalloutAnchorStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('正确渲染工作区顶层卡片、当前激活构件胶囊与报告章节', () => {
    render(<InteractiveCalloutWorkspaceCard />);

    expect(
      screen.getByTestId('interactive-callout-workspace-card')
    ).toBeInTheDocument();
    expect(screen.getByTestId('active-anchor-badge')).toHaveTextContent(
      '聚焦: 桁架根部支座节点 (Truss Heel)'
    );

    expect(screen.getByTestId('report-section-1')).toBeInTheDocument();
    expect(screen.getByTestId('report-section-2')).toBeInTheDocument();
    expect(screen.getByTestId('report-section-3')).toBeInTheDocument();

    expect(
      screen.getByTestId('visual-evidence-viewport-container')
    ).toBeInTheDocument();
  });

  it('点击左侧引文芯片能够聚焦目标构件并更新底部证据上下文', () => {
    render(<InteractiveCalloutWorkspaceCard />);

    const dbChip = screen.getByTestId('callout-chip-anchor-db-pool-02');
    fireEvent.click(dbChip);

    expect(useCalloutAnchorStore.getState().activeAnchorId).toBe(
      'anchor-db-pool-02'
    );
    expect(screen.getByTestId('active-anchor-badge')).toHaveTextContent(
      '数据库异步连接池 (DatabasePool)'
    );

    const detailCard = screen.getByTestId('callout-evidence-detail-card');
    expect(detailCard).toHaveTextContent('service.core.DatabasePool');
    expect(detailCard).toHaveTextContent('pool acquisition timeout occurs');
  });

  it('点击右侧构件节点能够反向联动聚焦左侧对应章节与引文', () => {
    render(<InteractiveCalloutWorkspaceCard />);

    const payBtnComponent = screen.getByTestId(
      'viewport-component-anchor-pay-btn-03'
    );
    fireEvent.click(payBtnComponent);

    expect(useCalloutAnchorStore.getState().activeAnchorId).toBe(
      'anchor-pay-btn-03'
    );
    expect(screen.getByTestId('active-anchor-badge')).toHaveTextContent(
      '结算提交交互卡片 (CheckoutButton)'
    );

    const detailCard = screen.getByTestId('callout-evidence-detail-card');
    expect(detailCard).toHaveTextContent('#btn-checkout-primary');
    expect(detailCard).toHaveTextContent('WCAG AAA');
  });

  it('点击视口全貌复位按钮能够复位视口变换矩阵', () => {
    render(<InteractiveCalloutWorkspaceCard />);

    const resetBtn = screen.getByTestId('reset-viewport-btn');
    fireEvent.click(resetBtn);

    expect(useCalloutAnchorStore.getState().viewportTransform).toEqual({
      translateX: 0,
      translateY: 0,
      scale: 1,
    });
    expect(useCalloutAnchorStore.getState().activeAnchorId).toBeNull();
  });
});
