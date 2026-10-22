import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VisualVersionRollbackDeck } from '../VisualVersionRollbackDeck';
import { useElementEditorStore } from '../useElementEditorStore';
import { InspectorElementInfo } from '../elementEditorTypes';

describe('VisualVersionRollbackDeck', () => {
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

  it('初始状态下悔棋与重做按钮应处于禁用状态', () => {
    render(<VisualVersionRollbackDeck />);

    const undoBtn = screen.getByRole('button', { name: /悔棋/i });
    const redoBtn = screen.getByRole('button', { name: /重做/i });

    expect(undoBtn).toBeDisabled();
    expect(redoBtn).toBeDisabled();
    expect(screen.getByText('v1')).toBeInTheDocument();
  });

  it('产生新修改后能点击悔棋原子回退', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('按钮变透明', 'style');

    render(<VisualVersionRollbackDeck />);

    const undoBtn = screen.getByRole('button', { name: /悔棋/i });
    expect(undoBtn).not.toBeDisabled();

    fireEvent.click(undoBtn);
    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(0);
  });

  it('点击版本号能展开时光机抽屉并支持按快照回滚', () => {
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('版本2', 'style');
    useElementEditorStore.getState().setSelectedElement(dummyElement);
    useElementEditorStore.getState().applyMicroPatch('版本3', 'content');

    render(<VisualVersionRollbackDeck />);

    const historyBtn = screen.getByRole('button', { name: /版本历史/i });
    fireEvent.click(historyBtn);

    expect(screen.getByTestId('snapshot-history-popover')).toBeInTheDocument();
    expect(screen.getByText(/共 3 个快照/)).toBeInTheDocument();

    // 点击 v1 回退
    const v1Btn = screen.getByText('初始工件生成');
    fireEvent.click(v1Btn);

    expect(useElementEditorStore.getState().currentSnapshotIndex).toBe(0);
  });
});
