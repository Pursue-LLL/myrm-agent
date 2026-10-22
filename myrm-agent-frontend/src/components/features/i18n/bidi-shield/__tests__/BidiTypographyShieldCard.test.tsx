import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BidiTypographyShieldCard } from '../BidiTypographyShieldCard';
import { useBidiShieldStore } from '../useBidiShieldStore';

describe('BidiTypographyShieldCard', () => {
  beforeEach(() => {
    useBidiShieldStore.getState().resetToDefault();
    vi.restoreAllMocks();
  });

  it('正确渲染卡片头部、当前有效方向与对比视窗', () => {
    render(<BidiTypographyShieldCard />);

    expect(
      screen.getByTestId('bidi-typography-shield-card')
    ).toBeInTheDocument();
    expect(screen.getByTestId('effective-direction-badge')).toHaveTextContent(
      '方向: RTL'
    );
    expect(
      screen.getByTestId('unshielded-text-preview')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('bidi-isolated-container')
    ).toBeInTheDocument();
  });

  it('点击方向模式按钮能够切换为强制 LTR 或 RTL', () => {
    render(<BidiTypographyShieldCard />);

    const ltrBtn = screen.getByTestId('direction-mode-btn-ltr');
    fireEvent.click(ltrBtn);

    expect(useBidiShieldStore.getState().direction).toBe('ltr');
    expect(screen.getByTestId('effective-direction-badge')).toHaveTextContent(
      '方向: LTR'
    );
  });

  it('点击 Windows 字体加固按钮能够翻转防御状态', () => {
    render(<BidiTypographyShieldCard />);

    const shieldBtn = screen.getByTestId('toggle-windows-shield-btn');
    fireEvent.click(shieldBtn);

    expect(
      useBidiShieldStore.getState().isWindowsTypographyShieldActive
    ).toBe(false);

    fireEvent.click(shieldBtn);
    expect(
      useBidiShieldStore.getState().isWindowsTypographyShieldActive
    ).toBe(true);
  });

  it('点击快速预设按钮能够更新当前测试文本与书写方向', () => {
    render(<BidiTypographyShieldCard />);

    const presetZhBtn = screen.getByTestId('load-preset-btn-preset-zh-tech');
    fireEvent.click(presetZhBtn);

    expect(useBidiShieldStore.getState().direction).toBe('ltr');
    expect(screen.getByTestId('effective-direction-badge')).toHaveTextContent(
      '方向: LTR'
    );
    expect(
      screen.getByTestId('unshielded-text-preview')
    ).toHaveTextContent('padding-inline-start');
  });

  it('在文本输入框中输入新文本实时反映在对比容器中', () => {
    render(<BidiTypographyShieldCard />);

    const input = screen.getByLabelText(/双向混合测试文本/);
    fireEvent.change(input, { target: { value: 'اختبار تجريبي جديد' } });

    expect(useBidiShieldStore.getState().customInputText).toBe(
      'اختبار تجريبي جديد'
    );
    expect(
      screen.getByTestId('unshielded-text-preview')
    ).toHaveTextContent('اختبار تجريبي جديد');
  });

  it('点击重置按钮能够还原为初始默认阿语混合样本', () => {
    render(<BidiTypographyShieldCard />);

    const ltrBtn = screen.getByTestId('direction-mode-btn-ltr');
    fireEvent.click(ltrBtn);

    const resetBtn = screen.getByTestId('reset-bidi-btn');
    fireEvent.click(resetBtn);

    expect(useBidiShieldStore.getState().direction).toBe('auto');
  });
});
