import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThreeModePermissionMatrixDeck } from '../ThreeModePermissionMatrixDeck';
import { useThreeModeStore } from '../useThreeModeStore';

describe('ThreeModePermissionMatrixDeck 组件单测', () => {
  beforeEach(() => {
    useThreeModeStore.setState({
      currentMode: 'ask',
      isMatrixOpen: true,
    });
  });

  it('当 isMatrixOpen 为 false 时不渲染任何抽屉元素', () => {
    useThreeModeStore.setState({ isMatrixOpen: false });
    const { container } = render(<ThreeModePermissionMatrixDeck />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('three-mode-permission-matrix-deck')).not.toBeInTheDocument();
  });

  it('当 isMatrixOpen 为 true 时完整呈现三态安全说明与三列对比卡片', () => {
    render(<ThreeModePermissionMatrixDeck />);

    expect(screen.getByTestId('three-mode-permission-matrix-deck')).toBeInTheDocument();
    expect(screen.getByText('三态心智模式安全说明')).toBeInTheDocument();
    expect(screen.getByText('Ask 问一问')).toBeInTheDocument();
    expect(screen.getByText('Plan 想一想')).toBeInTheDocument();
    expect(screen.getByText('Craft 做一做')).toBeInTheDocument();

    // 检查权限清单项
    expect(screen.getAllByText('修改本地文件').length).toBe(3);
    expect(screen.getAllByText('执行命令行脚本').length).toBe(3);
    expect(screen.getAllByText('强制先出计划').length).toBe(3);
  });

  it('点击其他模式下的切换按钮能热换挡并自动关闭抽屉', () => {
    render(<ThreeModePermissionMatrixDeck />);

    const switchButtons = screen.getAllByRole('button', { name: '切换到此模式' });
    // 第一个切换按钮是针对 Plan 模式
    fireEvent.click(switchButtons[0]);

    expect(useThreeModeStore.getState().currentMode).toBe('plan');
    expect(useThreeModeStore.getState().isMatrixOpen).toBe(false);
  });

  it('点击关闭按钮关闭权限抽屉', () => {
    render(<ThreeModePermissionMatrixDeck />);

    const closeBtn = screen.getByRole('button', { name: '关闭说明' });
    fireEvent.click(closeBtn);

    expect(useThreeModeStore.getState().isMatrixOpen).toBe(false);
  });
});
