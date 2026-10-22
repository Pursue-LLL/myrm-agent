import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { NonIntrusiveFallbackPillBadge } from '../NonIntrusiveFallbackPillBadge';
import { useGracefulDegradationStore } from '../useGracefulDegradationStore';
import { DegradationEvent } from '../gracefulDegradationTypes';

describe('NonIntrusiveFallbackPillBadge', () => {
  const baseEvent: DegradationEvent = {
    id: 'deg-test-1',
    componentId: 'comp-search',
    componentName: '网络检索集群',
    severity: 'warning',
    title: '网络检索超时熔断',
    explanation: '上游检索节点响应超时，已无缝切换至本地向量知识库回答。',
    fallbackActive: true,
    fallbackActionLabel: '已切换至知识库',
    recoveryEtaSec: 25,
    timestamp: Date.now(),
  };

  beforeEach(() => {
    useGracefulDegradationStore.getState().reset();
    useGracefulDegradationStore.setState({
      activeDegradations: {
        'deg-test-1': baseEvent,
      },
    });
  });

  it('renders compact pill badge with fallback message', () => {
    render(<NonIntrusiveFallbackPillBadge event={baseEvent} />);

    expect(screen.getByTestId('fallback-pill-deg-test-1')).toBeInTheDocument();
    expect(
      screen.getByText(/网络检索集群暂时拥堵，已无缝切换至降级策略回答/),
    ).toBeInTheDocument();
    expect(screen.getByText('查看详情')).toBeInTheDocument();
  });

  it('toggles detail panel when user clicks expand button', () => {
    render(<NonIntrusiveFallbackPillBadge event={baseEvent} />);

    const expandBtn = screen.getByRole('button', { name: '展开降级详情' });
    act(() => {
      fireEvent.click(expandBtn);
    });

    expect(screen.getByTestId('fallback-detail-panel')).toBeInTheDocument();
    expect(screen.getByText('网络检索超时熔断')).toBeInTheDocument();
    expect(
      screen.getByText(
        '上游检索节点响应超时，已无缝切换至本地向量知识库回答。',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('已切换至知识库')).toBeInTheDocument();
    expect(screen.getByText(/断路器自愈冷却 ~25s/)).toBeInTheDocument();

    // 收起详情
    const collapseBtn = screen.getByRole('button', { name: '收起降级详情' });
    act(() => {
      fireEvent.click(collapseBtn);
    });

    expect(screen.queryByTestId('fallback-detail-panel')).toBeNull();
  });

  it('calls onRetryProbe and resolves degradation on close click', () => {
    const handleRetry = vi.fn();
    render(
      <NonIntrusiveFallbackPillBadge
        event={baseEvent}
        onRetryProbe={handleRetry}
      />,
    );

    // 展开并点击重试
    const expandBtn = screen.getByRole('button', { name: '展开降级详情' });
    act(() => {
      fireEvent.click(expandBtn);
    });

    const retryBtn = screen.getByRole('button', { name: /重新探测/ });
    act(() => {
      fireEvent.click(retryBtn);
    });

    expect(handleRetry).toHaveBeenCalledWith(baseEvent);

    // 点击关闭胶囊
    const closeBtn = screen.getByRole('button', { name: '关闭降级说明徽标' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(
      useGracefulDegradationStore.getState().activeDegradations['deg-test-1'],
    ).toBeUndefined();
  });
});
