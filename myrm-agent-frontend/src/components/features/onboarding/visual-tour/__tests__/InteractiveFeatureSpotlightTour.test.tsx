import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InteractiveFeatureSpotlightTour } from '../InteractiveFeatureSpotlightTour';
import { useVisualTourStore } from '../useVisualTourStore';

describe('InteractiveFeatureSpotlightTour', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useVisualTourStore.getState().resetOnboardingState();
  });

  it('当 isTourActive 为 false 时不应渲染任何 DOM', () => {
    useVisualTourStore.setState({ isTourActive: false });
    const { container } = render(<InteractiveFeatureSpotlightTour />);
    expect(container.firstChild).toBeNull();
  });

  it('激活漫游时应展示当前指引步骤、徽章文本与步骤计数', () => {
    useVisualTourStore.setState({ isTourActive: true, currentStepIndex: 0 });
    render(<InteractiveFeatureSpotlightTour />);

    expect(screen.getByRole('dialog', { name: '功能漫游指引' })).toBeInTheDocument();
    expect(screen.getByText('智能体分身快速切换')).toBeInTheDocument();
    expect(screen.getByText('核心枢纽')).toBeInTheDocument();
    expect(screen.getByText(/1 \/ \d+/)).toBeInTheDocument();
  });

  it('点击下一步按钮应正确跳转至下一引导步骤', () => {
    useVisualTourStore.setState({ isTourActive: true, currentStepIndex: 0 });
    render(<InteractiveFeatureSpotlightTour />);

    const nextBtn = screen.getByRole('button', { name: /下一步/i });
    fireEvent.click(nextBtn);

    expect(useVisualTourStore.getState().currentStepIndex).toBe(1);
  });

  it('点击跳过引导按钮应关闭漫游窗口', () => {
    useVisualTourStore.setState({ isTourActive: true, currentStepIndex: 0 });
    render(<InteractiveFeatureSpotlightTour />);

    const skipBtn = screen.getByRole('button', { name: '跳过引导' });
    fireEvent.click(skipBtn);

    expect(useVisualTourStore.getState().isTourActive).toBe(false);
  });

  it('按下 Escape 键应安全跳过漫游', () => {
    useVisualTourStore.setState({ isTourActive: true, currentStepIndex: 0 });
    render(<InteractiveFeatureSpotlightTour />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useVisualTourStore.getState().isTourActive).toBe(false);
  });
});
