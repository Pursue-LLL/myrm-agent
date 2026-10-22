import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { SilentDaemonStatusBadge } from '../SilentDaemonStatusBadge';
import { useProgressiveBootStore } from '../useProgressiveBootStore';

describe('SilentDaemonStatusBadge', () => {
  beforeEach(() => {
    act(() => {
      useProgressiveBootStore.getState().resetBootState();
    });
  });

  it('在初始状态下展示 5 项服务静默就绪与零阻断提示', () => {
    render(<SilentDaemonStatusBadge />);

    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/项服务静默就绪/)).toBeInTheDocument();
    expect(screen.getByText('零阻断平滑就绪')).toBeInTheDocument();
  });

  it('点击徽标能够触发抽屉状态切换', () => {
    render(<SilentDaemonStatusBadge />);

    const button = screen.getByRole('button', {
      name: '查看后台静默服务与渐进能力披露抽屉',
    });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    act(() => {
      fireEvent.click(button);
    });

    expect(useProgressiveBootStore.getState().isDrawerOpen).toBe(true);
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });

  it('当存在被静默拦截的通知时，正确展示通知气泡', () => {
    act(() => {
      useProgressiveBootStore.getState().suppressBlockingModal({
        title: '静默插件提示',
        source: 'PluginManager',
        severity: 'info',
      });
    });

    render(<SilentDaemonStatusBadge />);
    expect(screen.getByText('1 条已静默')).toBeInTheDocument();
  });
});
