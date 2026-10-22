import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ProgressiveDisclosureDrawer } from '../ProgressiveDisclosureDrawer';
import { useProgressiveBootStore } from '../useProgressiveBootStore';

describe('ProgressiveDisclosureDrawer', () => {
  beforeEach(() => {
    act(() => {
      useProgressiveBootStore.getState().resetBootState();
    });
  });

  it('当 isDrawerOpen 为 false 时不渲染任何内容', () => {
    const { container } = render(<ProgressiveDisclosureDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('当 isDrawerOpen 为 true 时渲染抽屉主体与披露档位切换项', () => {
    act(() => {
      useProgressiveBootStore.getState().toggleDrawer(true);
    });

    render(<ProgressiveDisclosureDrawer />);

    expect(
      screen.getByRole('region', { name: '能力披露与后台静默控制中心' })
    ).toBeInTheDocument();
    expect(screen.getByText('渐进式能力披露与服务状态')).toBeInTheDocument();
    expect(screen.getByText('极简稳健档')).toBeInTheDocument();
    expect(screen.getByText('标准生产档')).toBeInTheDocument();
    expect(screen.getByText('底层专家档')).toBeInTheDocument();
    expect(screen.getByText('智能路由网关')).toBeInTheDocument();
  });

  it('点击不同档位能够切换当前激活的 tier', () => {
    act(() => {
      useProgressiveBootStore.getState().toggleDrawer(true);
    });

    render(<ProgressiveDisclosureDrawer />);

    const standardBtn = screen.getByText('标准生产档').closest('button');
    expect(standardBtn).not.toBeNull();

    act(() => {
      if (standardBtn) {
        fireEvent.click(standardBtn);
      }
    });

    expect(useProgressiveBootStore.getState().tier).toBe('standard');
  });

  it('能够关闭抽屉以及移除单条静默通知', () => {
    let noticeId = '';
    act(() => {
      useProgressiveBootStore.getState().toggleDrawer(true);
      noticeId = useProgressiveBootStore.getState().suppressBlockingModal({
        title: '静默警告通知',
        source: 'SecurityAudit',
        severity: 'warning',
        details: '未检测到证书异常',
      });
    });

    render(<ProgressiveDisclosureDrawer />);

    expect(screen.getByText('静默警告通知')).toBeInTheDocument();
    expect(screen.getByText('未检测到证书异常')).toBeInTheDocument();

    const deleteBtn = screen.getByRole('button', { name: '移除此条通知' });
    act(() => {
      fireEvent.click(deleteBtn);
    });

    expect(screen.queryByText('静默警告通知')).toBeNull();

    const closeBtn = screen.getByRole('button', { name: '关闭抽屉' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useProgressiveBootStore.getState().isDrawerOpen).toBe(false);
  });
});
