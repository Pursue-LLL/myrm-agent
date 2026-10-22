/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TouchFriendlySelectionList } from '../TouchFriendlySelectionList';
import type { TouchOptionItem } from '../mobileCockpitTypes';

const mockOptions: TouchOptionItem[] = [
  {
    id: 'plan-a',
    label: '方案 A：轻量流式加载',
    description: '使用 SSE 增量推流，内存占用极低',
    badge: '推荐',
    shortcut: 'A',
  },
  {
    id: 'plan-b',
    label: '方案 B：全量快照拉取',
    description: '单次 HTTP 往返，适合高速网络',
    shortcut: 'B',
  },
  {
    id: 'plan-c',
    label: '方案 C：实验性 WebSocket 管道',
    description: '当前沙箱暂不支持',
    disabled: true,
  },
];

describe('TouchFriendlySelectionList Component', () => {
  it('handles single selection mode when option card is tapped', () => {
    const onChangeMock = vi.fn();

    render(
      <TouchFriendlySelectionList
        options={mockOptions}
        mode="single"
        selectedIds={['plan-a']}
        onChange={onChangeMock}
      />,
    );

    expect(screen.getByText('方案 A：轻量流式加载')).toBeDefined();
    expect(screen.getByText('推荐')).toBeDefined();

    const optionB = screen.getByTestId('touch-option-plan-b');
    fireEvent.click(optionB);

    expect(onChangeMock).toHaveBeenCalledWith(['plan-b']);
  });

  it('handles multiple selection mode and toggles items', () => {
    const onChangeMock = vi.fn();

    render(
      <TouchFriendlySelectionList
        options={mockOptions}
        mode="multiple"
        selectedIds={['plan-a']}
        onChange={onChangeMock}
      />,
    );

    const optionB = screen.getByTestId('touch-option-plan-b');
    fireEvent.click(optionB);
    expect(onChangeMock).toHaveBeenCalledWith(['plan-a', 'plan-b']);

    // Tapping already selected item deselects it
    const optionA = screen.getByTestId('touch-option-plan-a');
    fireEvent.click(optionA);
    expect(onChangeMock).toHaveBeenCalledWith([]);
  });

  it('triggers onConfirm callback with selected items in multiple mode', () => {
    const onConfirmMock = vi.fn();

    render(
      <TouchFriendlySelectionList
        options={mockOptions}
        mode="multiple"
        selectedIds={['plan-a', 'plan-b']}
        onChange={vi.fn()}
        onConfirm={onConfirmMock}
      />,
    );

    const confirmBtn = screen.getByTestId('selection-confirm-btn');
    fireEvent.click(confirmBtn);

    expect(onConfirmMock).toHaveBeenCalledWith(['plan-a', 'plan-b']);
  });

  it('ignores clicks on disabled options', () => {
    const onChangeMock = vi.fn();

    render(
      <TouchFriendlySelectionList
        options={mockOptions}
        mode="single"
        selectedIds={[]}
        onChange={onChangeMock}
      />,
    );

    const optionC = screen.getByTestId('touch-option-plan-c');
    fireEvent.click(optionC);

    expect(onChangeMock).not.toHaveBeenCalled();
  });
});
