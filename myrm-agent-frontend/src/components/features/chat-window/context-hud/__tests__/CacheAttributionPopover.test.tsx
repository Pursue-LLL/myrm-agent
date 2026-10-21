import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { CacheAttributionPopover } from '../CacheAttributionPopover';
import { useContextHudStore } from '../useContextHudStore';

describe('CacheAttributionPopover', () => {
  beforeEach(() => {
    act(() => {
      useContextHudStore.getState().resetStore();
    });
  });

  it('renders nothing when popover is closed', () => {
    const { container } = render(<CacheAttributionPopover />);
    expect(container.firstChild).toBeNull();
  });

  it('renders diagnostic report and telemetry overview when open', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-diag', {
        inputTokens: 20000,
        outputTokens: 4000,
        cachedReadTokens: 16000,
        contextLimit: 128000,
      });
      useContextHudStore.getState().togglePopover(true);
    });

    render(<CacheAttributionPopover chatId="chat-diag" />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Prompt Cache 命中归因与诊断')).toBeInTheDocument();
    expect(screen.getByText('缓存链路工作极佳')).toBeInTheDocument();
    expect(screen.getByText('健康分 100')).toBeInTheDocument();
    expect(screen.getByText('前缀缓存优化指导')).toBeInTheDocument();
    expect(screen.getByText('24.0k / 128.0k')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it('renders timestamp jitter warning diagnostics', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-jitter', {
        inputTokens: 10000,
        outputTokens: 2000,
        cachedReadTokens: 1000,
        turnIndex: 3,
        hasDynamicTime: true,
      });
      useContextHudStore.getState().togglePopover(true);
    });

    render(<CacheAttributionPopover chatId="chat-jitter" />);

    expect(screen.getByText('动态时间戳导致前缀抖动')).toBeInTheDocument();
    expect(screen.getByText('健康分 40')).toBeInTheDocument();
    expect(screen.getByText(/预计可节约开销: ≈/)).toBeInTheDocument();
  });

  it('triggers auto compact on one-click button click', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-compact-btn', {
        inputTokens: 10000,
        outputTokens: 2000,
        cachedReadTokens: 5000,
        contextLimit: 128000,
      });
      useContextHudStore.getState().togglePopover(true);
    });

    render(<CacheAttributionPopover chatId="chat-compact-btn" />);

    const compactBtn = screen.getByLabelText('一键触发自动压缩');
    act(() => {
      fireEvent.click(compactBtn);
    });

    const metrics = useContextHudStore.getState().metricsByChatId['chat-compact-btn'];
    expect(metrics.autoCompactState).toBe('active');
    expect(metrics.inputTokens).toBe(6000); // 10000 * 0.6
  });

  it('closes popover on close button and finish button click', () => {
    act(() => {
      useContextHudStore.getState().togglePopover(true);
    });

    const onClose = vi.fn();
    const { rerender } = render(<CacheAttributionPopover onClose={onClose} />);

    // Click top close button
    const closeBtn = screen.getByLabelText('关闭诊断卡片');
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(useContextHudStore.getState().isPopoverOpen).toBe(false);

    // Reopen and click footer finish button
    act(() => {
      useContextHudStore.getState().togglePopover(true);
    });
    rerender(<CacheAttributionPopover onClose={onClose} />);

    const finishBtn = screen.getByText('完成查看');
    act(() => {
      fireEvent.click(finishBtn);
    });

    expect(onClose).toHaveBeenCalledTimes(2);
    expect(useContextHudStore.getState().isPopoverOpen).toBe(false);
  });

  it('closes popover on Escape key press and backdrop click', () => {
    act(() => {
      useContextHudStore.getState().togglePopover(true);
    });

    render(<CacheAttributionPopover />);

    // Press Escape
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useContextHudStore.getState().isPopoverOpen).toBe(false);

    // Reopen and click backdrop
    act(() => {
      useContextHudStore.getState().togglePopover(true);
    });

    const backdrop = screen.getByTestId('cache-attribution-backdrop');
    act(() => {
      fireEvent.click(backdrop);
    });
    expect(useContextHudStore.getState().isPopoverOpen).toBe(false);
  });
});
