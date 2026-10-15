import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { InPlacePartialRefinementPopover } from '../InPlacePartialRefinementPopover';
import { useWorkbenchStore } from '../useWorkbenchStore';
import { SelectionRange } from '../workbenchTypes';

describe('InPlacePartialRefinementPopover component', () => {
  const mockRange: SelectionRange = {
    startOffset: 10,
    endOffset: 40,
    selectedText: '智能体端侧渗透率将呈现高增长态势',
    contextBefore: '预测2026下半年',
    contextAfter: '。预计在金融与政企',
  };

  beforeEach(() => {
    act(() => {
      useWorkbenchStore.getState().resetState();
    });
  });

  it('renders null when there is no active selection', () => {
    const { container } = render(<InPlacePartialRefinementPopover />);
    expect(container.firstChild).toBeNull();
  });

  it('renders popover with selected snippet when selection is active', () => {
    act(() => {
      useWorkbenchStore.getState().setSelection(mockRange);
    });

    render(<InPlacePartialRefinementPopover />);

    expect(
      screen.getByTestId('in-place-partial-refinement-popover')
    ).toBeInTheDocument();
    expect(screen.getByText('划选就地重构精修')).toBeInTheDocument();
    expect(
      screen.getByText('智能体端侧渗透率将呈现高增长态势')
    ).toBeInTheDocument();
    expect(screen.getByText('预计节省 90%+ Token')).toBeInTheDocument();
  });

  it('submits instruction and transitions to preview state', async () => {
    act(() => {
      useWorkbenchStore.getState().setSelection(mockRange);
    });

    render(<InPlacePartialRefinementPopover />);

    const textarea = screen.getByPlaceholderText(
      /输入针对选中区域的微调指令/
    );
    fireEvent.change(textarea, {
      target: { value: '改为保守估值，补充汇率风险准备金' },
    });

    const submitBtn = screen.getByRole('button', { name: '提交局部重构' });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByTestId('refinement-preview-section')
      ).toBeInTheDocument();
    });

    expect(screen.getByText('替换预览 (Diff Preview):')).toBeInTheDocument();
    expect(screen.getByText(/节省 \d+% 算力 Token/)).toBeInTheDocument();
  });

  it('applies in-place replacement when accept button is clicked', async () => {
    act(() => {
      useWorkbenchStore.getState().setSelection(mockRange);
    });

    render(<InPlacePartialRefinementPopover />);

    const textarea = screen.getByPlaceholderText(
      /输入针对选中区域的微调指令/
    );
    fireEvent.change(textarea, {
      target: { value: '改为稳健精简' },
    });

    const submitBtn = screen.getByRole('button', { name: '提交局部重构' });
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: '采纳就地替换' })
      ).toBeInTheDocument();
    });

    const acceptBtn = screen.getByRole('button', { name: '采纳就地替换' });
    act(() => {
      fireEvent.click(acceptBtn);
    });

    expect(useWorkbenchStore.getState().refinementStatus).toBe('applied');
    expect(useWorkbenchStore.getState().currentSelection).toBeNull();
  });

  it('cancels refinement on dismiss button click', () => {
    act(() => {
      useWorkbenchStore.getState().setSelection(mockRange);
    });

    render(<InPlacePartialRefinementPopover />);

    const cancelBtn = screen.getByRole('button', { name: '取消局部编辑' });
    act(() => {
      fireEvent.click(cancelBtn);
    });

    expect(useWorkbenchStore.getState().refinementStatus).toBe('rejected');
    expect(useWorkbenchStore.getState().currentSelection).toBeNull();
  });
});
