import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { FireAndForgetDispatchBar } from '../FireAndForgetDispatchBar';
import { useLongTaskNotifyStore } from '../useLongTaskNotifyStore';

describe('FireAndForgetDispatchBar component', () => {
  beforeEach(() => {
    act(() => {
      useLongTaskNotifyStore.getState().resetState();
    });
  });

  it('renders null when dispatch modal is closed', () => {
    const { container } = render(<FireAndForgetDispatchBar />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dispatch modal with environment info and notification options when open', () => {
    act(() => {
      useLongTaskNotifyStore.getState().openDispatchModal();
    });

    render(<FireAndForgetDispatchBar />);

    expect(
      screen.getByTestId('fire-and-forget-dispatch-modal')
    ).toBeInTheDocument();
    expect(
      screen.getByText('碎片时间长任务「发完走人」确认')
    ).toBeInTheDocument();
    expect(screen.getByText('常驻云端独立沙箱')).toBeInTheDocument();
    expect(screen.getByText(/约 3分钟 \(地铁到站前备好\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/允许 Web Push 浏览器与移动端推送通知/)
    ).toBeInTheDocument();
    expect(screen.getByText('系统原生桌面通知')).toBeInTheDocument();
  });

  it('modifies inputs and submits long task dispatch successfully', () => {
    act(() => {
      useLongTaskNotifyStore.getState().openDispatchModal();
    });

    render(<FireAndForgetDispatchBar />);

    const titleInput = screen.getByLabelText('任务名称');
    fireEvent.change(titleInput, {
      target: { value: '午休碎片时间竞品盘点' },
    });

    const submitBtn = screen.getByRole('button', {
      name: '发完走人立即派发',
    });
    act(() => {
      fireEvent.click(submitBtn);
    });

    expect(useLongTaskNotifyStore.getState().isDispatchModalOpen).toBe(false);
    expect(useLongTaskNotifyStore.getState().activeTask?.title).toBe(
      '午休碎片时间竞品盘点'
    );
    expect(useLongTaskNotifyStore.getState().activeTask?.status).toBe(
      'running_unattended'
    );
  });

  it('closes dispatch modal when close button is clicked', () => {
    act(() => {
      useLongTaskNotifyStore.getState().openDispatchModal();
    });

    render(<FireAndForgetDispatchBar />);

    const closeBtn = screen.getByRole('button', {
      name: '关闭长任务派发窗口',
    });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useLongTaskNotifyStore.getState().isDispatchModalOpen).toBe(false);
  });
});
