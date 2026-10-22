import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ElementVisualEditorContainer } from '../ElementVisualEditorContainer';
import { useElementEditorStore } from '../useElementEditorStore';

describe('ElementVisualEditorContainer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useElementEditorStore.getState().resetStore();
  });

  it('应正确渲染工件总控容器、顶栏模式切换栏与预览内容', () => {
    render(<ElementVisualEditorContainer />);

    expect(screen.getByTestId('element-visual-editor-container')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /点选编辑/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /纯净预览/i })).toBeInTheDocument();
    expect(screen.getByText(/AI 智能设计与代码工件画布/)).toBeInTheDocument();
    expect(screen.getByText(/立即采纳方案/)).toBeInTheDocument();
  });

  it('点击纯净预览能切换只读交互模式', () => {
    render(<ElementVisualEditorContainer />);

    const previewBtn = screen.getByRole('button', { name: /纯净预览/i });
    fireEvent.click(previewBtn);

    expect(useElementEditorStore.getState().mode).toBe('preview');
    expect(screen.getByText('只读交互模式')).toBeInTheDocument();
  });

  it('点击预览区内的元素能选中并弹出就地微编辑浮层', () => {
    render(<ElementVisualEditorContainer />);

    const buttonEl = screen.getByText(/立即采纳方案/);
    fireEvent.click(buttonEl);

    expect(useElementEditorStore.getState().mode).toBe('in_place_editing');
    expect(screen.getByTestId('in-place-edit-popover')).toBeInTheDocument();
    expect(screen.getByText(/就地微调 <button>/)).toBeInTheDocument();
  });

  it('按下快捷键 Cmd+Z / Ctrl+Z 能触发悔棋 undo', () => {
    render(<ElementVisualEditorContainer />);

    // 制造一个新版本
    useElementEditorStore.getState().setSelectedElement({
      id: 'test-btn',
      tag: 'button',
      selector: 'button',
      xpath: '//button',
      rect: { top: 0, left: 0, width: 50, height: 20 },
      innerText: '按钮',
      classes: 'btn',
    });
    useElementEditorStore.getState().applyMicroPatch('变浅色', 'style');

    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(1);

    // 触发 Cmd+Z
    fireEvent.keyDown(window, {
      key: 'z',
      code: 'KeyZ',
      metaKey: true,
    });

    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(0);
  });
});
