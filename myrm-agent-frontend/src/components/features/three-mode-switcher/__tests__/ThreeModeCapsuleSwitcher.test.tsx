import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThreeModeCapsuleSwitcher } from '../ThreeModeCapsuleSwitcher';
import { useThreeModeStore } from '../useThreeModeStore';

describe('ThreeModeCapsuleSwitcher 组件单测', () => {
  beforeEach(() => {
    useThreeModeStore.setState({
      currentMode: 'ask',
      isMatrixOpen: false,
    });
  });

  it('渲染三态切换胶囊、心智描述与安全说明入口', () => {
    render(<ThreeModeCapsuleSwitcher />);

    expect(screen.getByTestId('three-mode-capsule-switcher')).toBeInTheDocument();
    expect(screen.getByText('问一问')).toBeInTheDocument();
    expect(screen.getByText('想一想')).toBeInTheDocument();
    expect(screen.getByText('做一做')).toBeInTheDocument();
    expect(screen.getByText('不改文件，安全阅读')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看权限说明' })).toBeInTheDocument();
  });

  it('点击做一做按钮切换当前工作模式为 craft 并更新心智口号', () => {
    render(<ThreeModeCapsuleSwitcher />);

    const craftBtn = screen.getByTestId('mode-capsule-btn-craft');
    fireEvent.click(craftBtn);

    expect(useThreeModeStore.getState().currentMode).toBe('craft');
    expect(screen.getByText('高效落地，直接产出')).toBeInTheDocument();
  });

  it('点击想一想按钮切换当前工作模式为 plan', () => {
    render(<ThreeModeCapsuleSwitcher />);

    const planBtn = screen.getByTestId('mode-capsule-btn-plan');
    fireEvent.click(planBtn);

    expect(useThreeModeStore.getState().currentMode).toBe('plan');
    expect(screen.getByText('先审计划，满意才动手')).toBeInTheDocument();
  });

  it('点击安全说明按钮能打开权限矩阵抽屉', () => {
    render(<ThreeModeCapsuleSwitcher />);

    const triggerBtn = screen.getByTestId('three-mode-security-matrix-trigger');
    fireEvent.click(triggerBtn);

    expect(useThreeModeStore.getState().isMatrixOpen).toBe(true);
  });
});
