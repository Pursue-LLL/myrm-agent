import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ThemeLayerDirectionInspectorCard } from '../ThemeLayerDirectionInspectorCard';
import { useThemeLayerInvariantStore } from '../useThemeLayerInvariantStore';

describe('ThemeLayerInvariant Integration End-to-End', () => {
  beforeEach(() => {
    act(() => {
      useThemeLayerInvariantStore.getState().reset();
    });
  });

  it('完整走通：违规主题渲染 -> 缺陷报警 -> 基线回归核查 -> 一键矫正自愈全链路', () => {
    // 1. 挂载带有浅色卡面调暗反直觉缺陷的初始配置
    render(
      <ThemeLayerDirectionInspectorCard
        initialLightCanvas="#ffffff"
        initialLightCard="#e7e7e8"
        initialDarkCanvas="#09090b"
        initialDarkCard="#18181b"
      />
    );

    // 2. 检查主面板是否敏锐捕捉到违规
    expect(screen.getByText('检测到层级反转缺陷')).toBeInTheDocument();
    expect(screen.getByText('违规发灰')).toBeInTheDocument();

    // 3. 打开预烘基线对比模态弹窗
    const openBaselineBtn = screen.getByRole('button', {
      name: /查看预烘基线对比报表/i,
    });
    act(() => {
      fireEvent.click(openBaselineBtn);
    });

    expect(
      screen.getByTestId('prebaked-baseline-diff-modal')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/警报：相比所选基线检测到层级方向反转回归/)
    ).toBeInTheDocument();
    expect(screen.getByText(/浅色主题发生反直觉回归/)).toBeInTheDocument();

    // 4. 点击弹窗底部的“完成审查并返回”
    const returnBtn = screen.getByRole('button', {
      name: /完成审查并返回/i,
    });
    act(() => {
      fireEvent.click(returnBtn);
    });

    expect(
      screen.queryByTestId('prebaked-baseline-diff-modal')
    ).not.toBeInTheDocument();

    // 5. 点击主卡片上的“一键矫正为无损浅色”
    const fixBtn = screen.getByRole('button', {
      name: /一键矫正为无损浅色/i,
    });
    act(() => {
      fireEvent.click(fixBtn);
    });

    // 6. 验证自愈修复：主状态变绿，违规报警消失
    expect(screen.getByText('双主题方向合格')).toBeInTheDocument();
    expect(
      screen.queryByText('检测到层级反转缺陷')
    ).not.toBeInTheDocument();

    // 7. 再次打开基线弹窗，比对结果自动变为无回归合规
    act(() => {
      fireEvent.click(openBaselineBtn);
    });
    expect(
      screen.getByText('与所选历史基线保持高度一致，无层级方向回归缺陷')
    ).toBeInTheDocument();
  });
});
