import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ThemeLayerDirectionInspectorCard } from '../ThemeLayerDirectionInspectorCard';
import { useThemeLayerInvariantStore } from '../useThemeLayerInvariantStore';

describe('ThemeLayerDirectionInspectorCard', () => {
  beforeEach(() => {
    act(() => {
      useThemeLayerInvariantStore.getState().reset();
    });
  });

  it('在初始双主题合规时呈现双主题合格标识与色值明度对比', () => {
    render(<ThemeLayerDirectionInspectorCard />);

    expect(
      screen.getByTestId('theme-layer-direction-inspector-card')
    ).toBeInTheDocument();
    expect(
      screen.getByText('双主题层级方向不变量与渲染色深度诊断')
    ).toBeInTheDocument();
    expect(screen.getByText('双主题方向合格')).toBeInTheDocument();

    expect(screen.getByTestId('light-mode-card')).toBeInTheDocument();
    expect(screen.getByTestId('dark-mode-card')).toBeInTheDocument();
  });

  it('当浅色卡面调暗发生反直觉发灰时，展示缺陷警报与一键矫正按钮', () => {
    render(
      <ThemeLayerDirectionInspectorCard
        initialLightCanvas="#ffffff"
        initialLightCard="#e7e7e8" // 错误调暗
        initialDarkCanvas="#09090b"
        initialDarkCard="#18181b"
      />
    );

    expect(screen.getByText('检测到层级反转缺陷')).toBeInTheDocument();
    expect(screen.getByText('违规发灰')).toBeInTheDocument();
    expect(screen.getByText(/浅色主题违规/)).toBeInTheDocument();

    const fixBtn = screen.getByRole('button', {
      name: /一键矫正为无损浅色/i,
    });
    expect(fixBtn).toBeInTheDocument();

    // 点击一键矫正
    act(() => {
      fireEvent.click(fixBtn);
    });

    expect(screen.getByText('双主题方向合格')).toBeInTheDocument();
    expect(
      screen.queryByText('检测到层级反转缺陷')
    ).not.toBeInTheDocument();
  });

  it('点击查看预烘基线对比报表能够打开对比模态弹窗', () => {
    render(<ThemeLayerDirectionInspectorCard />);

    const openBaselineBtn = screen.getByRole('button', {
      name: /查看预烘基线对比报表/i,
    });
    act(() => {
      fireEvent.click(openBaselineBtn);
    });

    expect(
      useThemeLayerInvariantStore.getState().isBaselineModalOpen
    ).toBe(true);
    expect(
      screen.getByTestId('prebaked-baseline-diff-modal')
    ).toBeInTheDocument();
  });
});
