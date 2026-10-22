import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { PrebakedBaselineDiffModal } from '../PrebakedBaselineDiffModal';
import { useThemeLayerInvariantStore } from '../useThemeLayerInvariantStore';

describe('PrebakedBaselineDiffModal', () => {
  beforeEach(() => {
    act(() => {
      useThemeLayerInvariantStore.getState().reset();
    });
  });

  it('在未打开或无评测报告时不渲染任何 DOM', () => {
    render(<PrebakedBaselineDiffModal />);
    expect(
      screen.queryByTestId('prebaked-baseline-diff-modal')
    ).not.toBeInTheDocument();
  });

  it('打开弹窗后完整呈现标题、基线版本切换组与当前版本实测状态', () => {
    act(() => {
      useThemeLayerInvariantStore
        .getState()
        .evaluateCurrentTheme('#ffffff', '#ffffff', '#09090b', '#18181b');
      useThemeLayerInvariantStore.getState().toggleBaselineModal(true);
    });

    render(<PrebakedBaselineDiffModal />);

    expect(
      screen.getByTestId('prebaked-baseline-diff-modal')
    ).toBeInTheDocument();
    expect(
      screen.getByText('预烘主题基线回归审查与对比')
    ).toBeInTheDocument();
    expect(screen.getByText('v0.9.0-clean')).toBeInTheDocument();
    expect(
      screen.getByText('v0.10.0-recessed-buggy')
    ).toBeInTheDocument();
    expect(
      screen.getByText('与所选历史基线保持高度一致，无层级方向回归缺陷')
    ).toBeInTheDocument();
  });

  it('支持切换对比基线版本', () => {
    act(() => {
      useThemeLayerInvariantStore
        .getState()
        .evaluateCurrentTheme('#ffffff', '#ffffff', '#09090b', '#18181b');
      useThemeLayerInvariantStore.getState().toggleBaselineModal(true);
    });

    render(<PrebakedBaselineDiffModal />);

    const buggyBtn = screen.getByRole('button', {
      name: /v0.10.0-recessed-buggy/i,
    });
    act(() => {
      fireEvent.click(buggyBtn);
    });

    expect(
      useThemeLayerInvariantStore.getState().selectedBaseline?.baselineVersion
    ).toBe('v0.10.0-recessed-buggy');
  });

  it('点击右上角关闭按钮或底部完成审查按钮关闭弹窗', () => {
    act(() => {
      useThemeLayerInvariantStore
        .getState()
        .evaluateCurrentTheme('#ffffff', '#ffffff', '#09090b', '#18181b');
      useThemeLayerInvariantStore.getState().toggleBaselineModal(true);
    });

    render(<PrebakedBaselineDiffModal />);

    const closeBtn = screen.getByRole('button', {
      name: '关闭基线对比弹窗',
    });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(
      useThemeLayerInvariantStore.getState().isBaselineModalOpen
    ).toBe(false);
  });
});
