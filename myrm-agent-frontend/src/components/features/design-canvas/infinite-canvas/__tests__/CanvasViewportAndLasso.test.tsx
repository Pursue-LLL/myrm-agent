import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { InfiniteDesignCanvasViewport } from '../InfiniteDesignCanvasViewport';
import { CanvasLassoSelectionOverlay } from '../CanvasLassoSelectionOverlay';
import { useInfiniteCanvasStore } from '../useInfiniteCanvasStore';

describe('InfiniteDesignCanvasViewport & CanvasLassoSelectionOverlay Components', () => {
  beforeEach(() => {
    useInfiniteCanvasStore.getState().resetCanvas();
  });

  describe('InfiniteDesignCanvasViewport', () => {
    it('renders initial design layers correctly', () => {
      render(<InfiniteDesignCanvasViewport />);

      expect(screen.getByText('2026 全栈智能体生产力峰会')).toBeDefined();
      expect(screen.getByText(/双击任意文本免 Token 直接改字/)).toBeDefined();
    });

    it('selects layer on click', () => {
      render(<InfiniteDesignCanvasViewport />);

      const titleNode = screen.getByText('2026 全栈智能体生产力峰会');
      fireEvent.mouseDown(titleNode);

      expect(useInfiniteCanvasStore.getState().selectedLayerId).toBe('layer_title');
    });

    it('enters inline edit mode on double click, modifies text, and commits on enter', () => {
      render(<InfiniteDesignCanvasViewport />);

      const titleNode = screen.getByText('2026 全栈智能体生产力峰会');
      // 双击启动免 Token 直编
      fireEvent.doubleClick(titleNode);

      expect(useInfiniteCanvasStore.getState().editingTextLayerId).toBe('layer_title');

      // 输入新标题
      const input = screen.getByDisplayValue('2026 全栈智能体生产力峰会');
      expect(input).toBeDefined();

      fireEvent.change(input, { target: { value: '2026 全球架构创新大会' } });
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

      // 验证文本更新且退出编辑模式
      expect(useInfiniteCanvasStore.getState().editingTextLayerId).toBeNull();
      expect(screen.getByText('2026 全球架构创新大会')).toBeDefined();
      expect(useInfiniteCanvasStore.getState().zeroTokenStats.inlineEditCount).toBe(1);
    });

    it('creates lasso selection box when alt key is pressed during mouse drag', () => {
      const { container } = render(<InfiniteDesignCanvasViewport />);
      const viewportEl = container.firstChild as HTMLDivElement;

      // 模拟 Alt+拖拽框选
      fireEvent.mouseDown(viewportEl, { clientX: 100, clientY: 100, altKey: true });
      fireEvent.mouseMove(viewportEl, { clientX: 400, clientY: 300, altKey: true });
      fireEvent.mouseUp(viewportEl);

      const lassoBox = useInfiniteCanvasStore.getState().activeLassoBox;
      expect(lassoBox).not.toBeNull();
      expect(lassoBox?.startX).toBeDefined();
      expect(lassoBox?.endX).toBeDefined();
    });
  });

  describe('CanvasLassoSelectionOverlay', () => {
    it('does not render when there is no active lasso box', () => {
      render(<CanvasLassoSelectionOverlay />);
      expect(screen.queryByText(/智能局部重绘/)).toBeNull();
    });

    it('renders overlay with layer counts and submits inpainting prompt', () => {
      // 设置选区
      act(() => {
        useInfiniteCanvasStore.getState().setLassoBox({
          startX: 50,
          startY: 50,
          endX: 600,
          endY: 150,
        });
      });

      render(<CanvasLassoSelectionOverlay />);

      expect(screen.getByText(/智能局部重绘 \(Inpainting\)/)).toBeDefined();
      expect(screen.getByText(/重绘目标:/)).toBeDefined();
      expect(screen.getByText(/已锁定/)).toBeDefined();

      const input = screen.getByPlaceholderText(/输入局部修改要求/);
      fireEvent.change(input, { target: { value: '把标题文字换成金色发光字体' } });

      const submitBtn = screen.getByRole('button', { name: /注入选区上下文并微调/ });
      fireEvent.click(submitBtn);

      expect(screen.getByText(/局部重绘上下文已反向注入对话/)).toBeDefined();
    });

    it('clears lasso box when close button is clicked', () => {
      act(() => {
        useInfiniteCanvasStore.getState().setLassoBox({
          startX: 50,
          startY: 50,
          endX: 200,
          endY: 200,
        });
      });

      render(<CanvasLassoSelectionOverlay />);

      const closeBtn = screen.getByRole('button', { name: '清除选区' });
      fireEvent.click(closeBtn);

      expect(useInfiniteCanvasStore.getState().activeLassoBox).toBeNull();
    });
  });
});
