import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DualTrackModeSwitcher } from '../DualTrackModeSwitcher';
import { useDualTrackStore } from '../useDualTrackStore';

describe('DualTrackModeSwitcher', () => {
  beforeEach(() => {
    useDualTrackStore.getState().resetAll();
  });

  it('正常渲染双轨视图切换器与两档模式按钮', () => {
    render(<DualTrackModeSwitcher />);
    expect(
      screen.getByTestId('dual-track-mode-switcher')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('switch-business-mode-btn')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('switch-engineering-mode-btn')
    ).toBeInTheDocument();
  });

  it('点击深度工程模式按钮，切换模式并触发回调', () => {
    const handleModeChange = vi.fn();
    render(<DualTrackModeSwitcher onModeChange={handleModeChange} />);

    const engBtn = screen.getByTestId('switch-engineering-mode-btn');
    fireEvent.click(engBtn);

    expect(handleModeChange).toHaveBeenCalledWith('engineering');
    expect(useDualTrackStore.getState().viewMode).toBe('engineering');
    expect(engBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('点击业务极简模式按钮，切回业务模式', () => {
    useDualTrackStore.setState({ viewMode: 'engineering' });
    render(<DualTrackModeSwitcher />);

    const bizBtn = screen.getByTestId('switch-business-mode-btn');
    fireEvent.click(bizBtn);

    expect(useDualTrackStore.getState().viewMode).toBe('business');
    expect(bizBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
