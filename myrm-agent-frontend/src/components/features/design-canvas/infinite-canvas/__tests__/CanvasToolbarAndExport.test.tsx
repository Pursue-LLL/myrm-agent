import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { CanvasToolbarAndExportDeck } from '../CanvasToolbarAndExportDeck';
import { useInfiniteCanvasStore } from '../useInfiniteCanvasStore';

describe('CanvasToolbarAndExportDeck Component', () => {
  beforeEach(() => {
    useInfiniteCanvasStore.getState().resetCanvas();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });
  });

  it('renders tool buttons, zoom indicator, and zero-token stats badge', () => {
    render(<CanvasToolbarAndExportDeck />);

    expect(screen.getByRole('button', { name: /选择与移动工具/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /智能框选局部重绘工具/ })).toBeDefined();
    expect(screen.getByText('100%')).toBeDefined();
    expect(screen.getByText(/免 Token 直编:/)).toBeDefined();
    expect(screen.getByText('0')).toBeDefined();
  });

  it('switches tool modes on click', () => {
    render(<CanvasToolbarAndExportDeck />);

    const lassoBtn = screen.getByRole('button', { name: /智能框选局部重绘工具/ });
    fireEvent.click(lassoBtn);
    expect(useInfiniteCanvasStore.getState().toolMode).toBe('lasso');

    const selectBtn = screen.getByRole('button', { name: /选择与移动工具/ });
    fireEvent.click(selectBtn);
    expect(useInfiniteCanvasStore.getState().toolMode).toBe('select');
  });

  it('controls canvas zoom levels via buttons', () => {
    render(<CanvasToolbarAndExportDeck />);

    const zoomInBtn = screen.getByRole('button', { name: /放大画布/ });
    fireEvent.click(zoomInBtn);
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1.1);

    const zoomOutBtn = screen.getByRole('button', { name: /缩小画布/ });
    fireEvent.click(zoomOutBtn);
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1);

    const resetBtn = screen.getByRole('button', { name: /重置缩放/ });
    fireEvent.click(resetBtn);
    expect(useInfiniteCanvasStore.getState().viewport.zoom).toBe(1);
  });

  it('updates zero-token savings badge when inline edits occur', () => {
    const { rerender } = render(<CanvasToolbarAndExportDeck />);

    // 模拟进行了 2 次免 Token 直编
    act(() => {
      useInfiniteCanvasStore.getState().startInlineTextEdit('layer_title');
      useInfiniteCanvasStore.getState().finishInlineTextEdit('全新标题');
      useInfiniteCanvasStore.getState().startInlineTextEdit('layer_desc');
      useInfiniteCanvasStore.getState().finishInlineTextEdit('全新说明');
    });

    rerender(<CanvasToolbarAndExportDeck />);

    expect(screen.getByText('2')).toBeDefined();
    expect(screen.getByText(/省 ~5,600 T/)).toBeDefined();
  });

  it('copies SVG markup to clipboard and triggers download on export', () => {
    // Mock URL.createObjectURL and link.click
    const createObjectURLMock = vi.fn().mockReturnValue('blob:test-svg');
    const revokeObjectURLMock = vi.fn();
    Object.assign(window.URL, {
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock,
    });

    render(<CanvasToolbarAndExportDeck />);

    // 复制 SVG
    const copyBtn = screen.getByRole('button', { name: /复制 SVG/ });
    fireEvent.click(copyBtn);
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
    expect(screen.getByText('已复制 SVG')).toBeDefined();

    // 导出 SVG
    const exportBtn = screen.getByRole('button', { name: /导出无损矢量/ });
    fireEvent.click(exportBtn);
    expect(createObjectURLMock).toHaveBeenCalled();
  });
});
