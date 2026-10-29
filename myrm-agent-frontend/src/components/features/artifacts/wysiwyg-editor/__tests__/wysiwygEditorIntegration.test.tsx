import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { WysiwygArtifactEditorOverlay } from '../WysiwygArtifactEditorOverlay';
import { useWysiwygEditorStore } from '../useWysiwygEditorStore';

describe('WysiwygArtifactEditor Integration End-to-End', () => {
  beforeEach(() => {
    act(() => {
      useWysiwygEditorStore.getState().reset();
    });
  });

  it('完整走通：进入快速微调 -> 选定标题 -> 行内修改文本 -> 样式调整 -> 零 Token 一键保存全流程', () => {
    render(<WysiwygArtifactEditorOverlay />);

    expect(
      screen.getByTestId('wysiwyg-artifact-editor-overlay')
    ).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();

    // 1. 点击“快速微调”按钮激活编辑模式
    const toggleBtn = screen.getByRole('button', { name: /快速微调/i });
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(useWysiwygEditorStore.getState().mode).toBe('editing');
    expect(screen.getByText('退出微调')).toBeInTheDocument();

    // 2. 模拟点击标题节点
    const titleNode = screen.getByTestId('editable-title-node');
    act(() => {
      fireEvent.click(titleNode);
    });

    expect(
      screen.getByTestId('floating-style-toolbar')
    ).toBeInTheDocument();
    expect(screen.getByText('h2.article-title')).toBeInTheDocument();

    // 3. 在行内输入框中直改标题文字
    const textInput = screen.getByDisplayValue('飞书文档自动化处理周报');
    act(() => {
      fireEvent.change(textInput, {
        target: { value: '自动化飞书多维表格知识库大屏' },
      });
    });

    expect(
      useWysiwygEditorStore.getState().selectedElement?.textContent
    ).toBe('自动化飞书多维表格知识库大屏');
    expect(screen.getByText('1 处未保存微调')).toBeInTheDocument();

    // 4. 在浮动控制板上切换字号为 XL
    const xlBtn = screen.getByRole('button', { name: 'XL' });
    act(() => {
      fireEvent.click(xlBtn);
    });

    expect(
      useWysiwygEditorStore.getState().selectedElement?.styles.fontSize
    ).toBe('24px');
    expect(screen.getByText('2 处未保存微调')).toBeInTheDocument();

    // 5. 点击“保存微调 (0 Token)”
    const saveBtn = screen.getByRole('button', {
      name: /保存微调 \(0 Token\)/i,
    });
    act(() => {
      fireEvent.click(saveBtn);
    });

    // 6. 验证结果：版本提升至 v2，未保存提示消失，0 Token 横幅出现
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(
      screen.queryByText(/未保存微调/)
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId('zero-token-save-banner')
    ).toBeInTheDocument();
    expect(
      screen.getByText('工件版本 v2 就地极速保存成功')
    ).toBeInTheDocument();
    expect(screen.getByText('0 Token 消耗')).toBeInTheDocument();

    // 模式自动切回 preview
    expect(useWysiwygEditorStore.getState().mode).toBe('preview');
  });

  it('支持在微调过程中点击“放弃”按钮还原所有就地改动', () => {
    render(<WysiwygArtifactEditorOverlay />);

    // 进入微调
    const toggleBtn = screen.getByRole('button', { name: /快速微调/i });
    act(() => {
      fireEvent.click(toggleBtn);
    });

    // 选中标题并修改文本
    const titleNode = screen.getByTestId('editable-title-node');
    act(() => {
      fireEvent.click(titleNode);
    });

    const textInput = screen.getByDisplayValue('飞书文档自动化处理周报');
    act(() => {
      fireEvent.change(textInput, {
        target: { value: '将被丢弃的未保存草稿' },
      });
    });

    expect(screen.getByText('1 处未保存微调')).toBeInTheDocument();

    // 点击放弃
    const discardBtn = screen.getByRole('button', { name: /放弃/i });
    act(() => {
      fireEvent.click(discardBtn);
    });

    expect(
      screen.queryByText(/未保存微调/)
    ).not.toBeInTheDocument();
    expect(useWysiwygEditorStore.getState().pendingMutations).toHaveLength(0);
  });
});
