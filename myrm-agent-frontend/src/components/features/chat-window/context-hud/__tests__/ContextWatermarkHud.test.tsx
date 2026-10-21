import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ContextWatermarkHud } from '../ContextWatermarkHud';
import { useContextHudStore } from '../useContextHudStore';

describe('ContextWatermarkHud', () => {
  beforeEach(() => {
    act(() => {
      useContextHudStore.getState().resetStore();
    });
  });

  it('renders default zero metrics HUD', () => {
    render(<ContextWatermarkHud />);

    expect(screen.getByTestId('context-watermark-hud')).toBeInTheDocument();
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('0%').length).toBeGreaterThanOrEqual(1);
  });

  it('renders full telemetry numbers when chat has metrics', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-telemetry', {
        inputTokens: 12000,
        outputTokens: 3000,
        cachedReadTokens: 9000,
        contextLimit: 128000,
      });
    });

    render(<ContextWatermarkHud chatId="chat-telemetry" />);

    expect(screen.getByText('12.0k')).toBeInTheDocument();
    expect(screen.getByText('3.0k')).toBeInTheDocument();
    expect(screen.getByText('9.0k')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument(); // 9000 / 12000
    expect(screen.getByText('12%')).toBeInTheDocument(); // 15000 / 128000
    expect(screen.getByText('auto')).toBeInTheDocument();
  });

  it('renders compact mode without cache hit details', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-compact', {
        inputTokens: 8000,
        outputTokens: 2000,
        cachedReadTokens: 6000,
      });
    });

    render(<ContextWatermarkHud chatId="chat-compact" compact />);

    expect(screen.getByText('8.0k')).toBeInTheDocument();
    expect(screen.getByText('2.0k')).toBeInTheDocument();
    // Cache percentage should not be rendered in compact mode
    expect(screen.queryByText('75%')).not.toBeInTheDocument();
  });

  it('renders critical watermark styles when usage exceeds 85%', () => {
    act(() => {
      useContextHudStore.getState().updateMetrics('chat-crit', {
        inputTokens: 90000,
        outputTokens: 5000,
        cachedReadTokens: 10000,
        contextLimit: 100000,
      });
    });

    render(<ContextWatermarkHud chatId="chat-crit" />);

    const watermarkText = screen.getByText('95%');
    expect(watermarkText).toHaveClass('text-rose-500');
  });

  it('triggers popover opening on button click', () => {
    const onOpenDiagnostics = vi.fn();

    // 1. With custom callback
    const { rerender } = render(
      <ContextWatermarkHud onOpenDiagnostics={onOpenDiagnostics} />,
    );

    const btn = screen.getByTestId('context-hud-trigger-button');
    fireEvent.click(btn);
    expect(onOpenDiagnostics).toHaveBeenCalledTimes(1);

    // 2. Default store dispatch
    rerender(<ContextWatermarkHud />);
    fireEvent.click(btn);
    expect(useContextHudStore.getState().isPopoverOpen).toBe(true);
  });
});
