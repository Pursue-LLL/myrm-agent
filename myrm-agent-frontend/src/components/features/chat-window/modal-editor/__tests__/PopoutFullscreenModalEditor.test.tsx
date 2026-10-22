import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { PopoutFullscreenModalEditor } from '../PopoutFullscreenModalEditor';
import { useModalEditorStore } from '../useModalEditorStore';

describe('PopoutFullscreenModalEditor', () => {
  beforeEach(() => {
    act(() => {
      useModalEditorStore.getState().resetStore();
    });
  });

  it('renders nothing when modal editor is closed', () => {
    const { container } = render(<PopoutFullscreenModalEditor />);
    expect(container.firstChild).toBeNull();
  });

  it('renders full modal editor interface when open', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('初始输入内容');
    });

    render(<PopoutFullscreenModalEditor />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('全屏 Markdown 撰写与长公文排版')).toBeInTheDocument();
    expect(screen.getByText('Ctrl+G')).toBeInTheDocument();
    expect(screen.getByText('需求规范 PRD')).toBeInTheDocument();
    expect(screen.getByText('故障排查报告')).toBeInTheDocument();
    expect(screen.getByText('架构重构方案')).toBeInTheDocument();
    expect(screen.getByText('公文方案润色')).toBeInTheDocument();

    const textarea = screen.getByTestId('modal-editor-textarea') as HTMLTextAreaElement;
    expect(textarea.value).toBe('初始输入内容');
  });

  it('updates text and calculates metrics dynamically', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('');
    });

    render(<PopoutFullscreenModalEditor />);

    const textarea = screen.getByTestId('modal-editor-textarea');
    fireEvent.change(textarea, { target: { value: '这是第一段公文内容\n第二行 PRD 100%' } });

    expect(useModalEditorStore.getState().content).toContain('这是第一段公文内容');
    expect(screen.getByText(/2 行/)).toBeInTheDocument();
  });

  it('inserts template on button click', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('原有内容');
    });

    render(<PopoutFullscreenModalEditor />);

    const prdBtn = screen.getByText('需求规范 PRD');
    fireEvent.click(prdBtn);

    const textarea = screen.getByTestId('modal-editor-textarea') as HTMLTextAreaElement;
    expect(textarea.value).toContain('原有内容');
    expect(textarea.value).toContain('产品需求规范 (PRD)');
  });

  it('toggles side-by-side preview panel', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('# 标题预览');
    });

    render(<PopoutFullscreenModalEditor />);

    expect(screen.queryByTestId('modal-editor-preview-panel')).not.toBeInTheDocument();

    const previewToggleBtn = screen.getByLabelText('切换双栏实时预览');
    fireEvent.click(previewToggleBtn);

    const previewPanel = screen.getByTestId('modal-editor-preview-panel');
    expect(previewPanel).toBeInTheDocument();
    expect(previewPanel).toHaveTextContent('# 标题预览');
  });

  it('dispatches external editor event on button click', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('外部编辑草稿');
    });

    const listener = vi.fn();
    window.addEventListener('myrm:open-external-editor', listener);

    render(<PopoutFullscreenModalEditor sessionId="chat_ext_1" />);

    const extBtn = screen.getByLabelText('拉起桌面外部编辑器');
    fireEvent.click(extBtn);

    expect(listener).toHaveBeenCalled();
    expect(useModalEditorStore.getState().isExternalEditorActive).toBe(true);

    window.removeEventListener('myrm:open-external-editor', listener);
  });

  it('confirms edit on button click and keyboard shortcut', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('待提交文本');
    });

    const onConfirm = vi.fn();
    const { rerender } = render(<PopoutFullscreenModalEditor onConfirm={onConfirm} />);

    // Click confirm button
    const confirmBtn = screen.getByTestId('modal-editor-confirm-button');
    fireEvent.click(confirmBtn);

    expect(onConfirm).toHaveBeenCalledWith('待提交文本');
    expect(useModalEditorStore.getState().isOpen).toBe(false);

    // Reopen and test shortcut Cmd+Enter
    act(() => {
      useModalEditorStore.getState().openEditor('快捷键文本');
    });
    rerender(<PopoutFullscreenModalEditor onConfirm={onConfirm} />);

    fireEvent.keyDown(window, { key: 'Enter', metaKey: true });
    expect(onConfirm).toHaveBeenCalledWith('快捷键文本');
    expect(useModalEditorStore.getState().isOpen).toBe(false);
  });

  it('cancels edit on close button, Escape key, and backdrop click', () => {
    act(() => {
      useModalEditorStore.getState().openEditor('原始安全文本');
      useModalEditorStore.getState().setContent('误删改后的文本');
    });

    const onCancel = vi.fn();
    const { rerender } = render(<PopoutFullscreenModalEditor onCancel={onCancel} />);

    // 1. Click X button
    const closeBtn = screen.getByLabelText('放弃修改并关闭');
    fireEvent.click(closeBtn);

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(useModalEditorStore.getState().isOpen).toBe(false);
    expect(useModalEditorStore.getState().content).toBe('原始安全文本');

    // 2. Escape key
    act(() => {
      useModalEditorStore.getState().openEditor('原始文本2');
    });
    rerender(<PopoutFullscreenModalEditor onCancel={onCancel} />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(2);
    expect(useModalEditorStore.getState().isOpen).toBe(false);

    // 3. Backdrop click
    act(() => {
      useModalEditorStore.getState().openEditor('原始文本3');
    });
    rerender(<PopoutFullscreenModalEditor onCancel={onCancel} />);

    const backdrop = screen.getByTestId('modal-editor-backdrop');
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(3);
    expect(useModalEditorStore.getState().isOpen).toBe(false);
  });
});
