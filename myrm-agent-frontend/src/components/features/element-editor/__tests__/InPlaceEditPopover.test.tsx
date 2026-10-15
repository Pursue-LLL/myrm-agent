import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InPlaceEditPopover } from '../InPlaceEditPopover';
import { useElementEditorStore } from '../useElementEditorStore';
import { InspectorElementInfo } from '../elementEditorTypes';

describe('InPlaceEditPopover', () => {
  const dummyElement: InspectorElementInfo = {
    id: 'btn-target',
    tag: 'button',
    selector: 'button#btn-target',
    xpath: '//button',
    rect: { top: 50, left: 100, width: 120, height: 40 },
    innerText: '立即购买',
    classes: 'btn btn-primary',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useElementEditorStore.getState().resetStore();
  });

  it('在无选中元素或非 in_place_editing 模式下不应渲染', () => {
    render(<InPlaceEditPopover />);
    expect(screen.queryByTestId('in-place-edit-popover')).not.toBeInTheDocument();
  });

  it('选中元素时应在对应位置弹出就地微编辑浮层', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    render(<InPlaceEditPopover />);

    expect(screen.getByTestId('in-place-edit-popover')).toBeInTheDocument();
    expect(screen.getByText(/就地微调 <button>/)).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/输入微调提示词/i)
    ).toBeInTheDocument();
  });

  it('输入提示词并点击应用补丁能更新快照历史', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    render(<InPlaceEditPopover />);

    const textarea = screen.getByPlaceholderText(/输入微调提示词/i);
    fireEvent.change(textarea, { target: { value: '按钮圆角增大到 16px' } });

    const applyBtn = screen.getByRole('button', { name: /应用补丁/i });
    fireEvent.click(applyBtn);

    expect(useElementEditorStore.getState().snapshots.length).toBe(2);
    expect(useElementEditorStore.getState().mode).toBe('inspect');
  });

  it('点击取消按钮能清空选区', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    render(<InPlaceEditPopover />);

    const cancelBtn = screen.getByRole('button', { name: /取消/i });
    fireEvent.click(cancelBtn);

    expect(useElementEditorStore.getState().selectedElement).toBeNull();
  });
});
