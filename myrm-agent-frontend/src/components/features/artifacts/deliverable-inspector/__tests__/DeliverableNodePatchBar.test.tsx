import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliverableNodePatchBar } from '../DeliverableNodePatchBar';
import type { DeliverableNode } from '../deliverableInspectorTypes';

describe('DeliverableNodePatchBar', () => {
  const mockNode: DeliverableNode = {
    id: 'slide-2',
    index: 2,
    title: '运营数据看板',
    summary: '展示各项核心转化指标',
    nodeType: 'slide',
    content: '## 运营数据看板\n- 指标 A: 80%\n- 指标 B: 95%',
  };

  it('renders null when targetNode is null', () => {
    const { container } = render(
      <DeliverableNodePatchBar
        targetNode={null}
        onApplyPatch={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders target node info and handles prompt submission', () => {
    const onApplyPatch = vi.fn();
    render(
      <DeliverableNodePatchBar
        targetNode={mockNode}
        onApplyPatch={onApplyPatch}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/局部针对性重做：运营数据看板/)).toBeDefined();
    expect(screen.getByText('#2')).toBeDefined();

    const input = screen.getByPlaceholderText(/输入微调要求/);
    fireEvent.change(input, { target: { value: '将指标 A 改为折线图' } });

    const submitBtn = screen.getByRole('button', { name: /定向重做/i });
    fireEvent.click(submitBtn);

    expect(onApplyPatch).toHaveBeenCalledTimes(1);
    expect(onApplyPatch).toHaveBeenCalledWith({
      nodeId: 'slide-2',
      targetedPrompt: '将指标 A 改为折线图',
      patchMode: 'refine_content',
    });
  });

  it('appends preset prompt when clicking preset chips', () => {
    render(
      <DeliverableNodePatchBar
        targetNode={mockNode}
        onApplyPatch={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const presetBtn = screen.getByRole('button', { name: '精简文案' });
    fireEvent.click(presetBtn);

    const input = screen.getByPlaceholderText(/输入微调要求/) as HTMLInputElement;
    expect(input.value).toBe('精简文案');
  });

  it('handles patch mode selection change', () => {
    const onApplyPatch = vi.fn();
    render(
      <DeliverableNodePatchBar
        targetNode={mockNode}
        onApplyPatch={onApplyPatch}
        onClose={vi.fn()}
      />,
    );

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'regenerate_node' } });

    const input = screen.getByPlaceholderText(/输入微调要求/);
    fireEvent.change(input, { target: { value: '重做整页版式' } });

    const submitBtn = screen.getByRole('button', { name: /定向重做/i });
    fireEvent.click(submitBtn);

    expect(onApplyPatch).toHaveBeenCalledWith({
      nodeId: 'slide-2',
      targetedPrompt: '重做整页版式',
      patchMode: 'regenerate_node',
    });
  });

  it('handles close button click', () => {
    const onClose = vi.fn();
    render(
      <DeliverableNodePatchBar
        targetNode={mockNode}
        onApplyPatch={vi.fn()}
        onClose={onClose}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: '关闭局部微调栏' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables input and shows patching spinner when isPatching is true', () => {
    render(
      <DeliverableNodePatchBar
        targetNode={mockNode}
        onApplyPatch={vi.fn()}
        onClose={vi.fn()}
        isPatching={true}
      />,
    );

    expect(screen.getByText('打补丁中...')).toBeDefined();
    const input = screen.getByPlaceholderText(/输入微调要求/);
    expect(input.hasAttribute('disabled')).toBe(true);
  });
});
