import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { CliCommandPreviewDrawer } from '../CliCommandPreviewDrawer';
import { useCliPassthroughStore } from '../useCliPassthroughStore';

describe('CliCommandPreviewDrawer', () => {
  beforeEach(() => {
    act(() => {
      useCliPassthroughStore.getState().resetStore();
    });
  });

  it('renders nothing when drawer is closed or activeCommand is null', () => {
    const { container } = render(<CliCommandPreviewDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer with visible_to_context command details', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('! npm test');
    });

    render(<CliCommandPreviewDrawer />);

    expect(screen.getByRole('region', { name: 'CLI 穿透执行抽屉' })).toBeInTheDocument();
    expect(screen.getByText('$ npm test')).toBeInTheDocument();
    expect(screen.getByText('上下文可见 · AI 感知')).toBeInTheDocument();
    expect(screen.getByText(/执行成功/)).toBeInTheDocument();
    expect(screen.getByText(/提示：以 ! 开头的命令输出会自动作为 \[USER_CMD_EXEC\]/)).toBeInTheDocument();
  });

  it('renders user_inspection_only mode properly', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('!! git status');
    });

    render(<CliCommandPreviewDrawer />);

    expect(screen.getByText('$ git status')).toBeInTheDocument();
    expect(screen.getByText('仅本地自省 · 0 Token 消耗')).toBeInTheDocument();
    expect(screen.getByText(/提示：以 !! 开头的命令输出仅供本地终端抽屉查看/)).toBeInTheDocument();
  });

  it('renders blocked_by_guard notification for dangerous command', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('! rm -rf /');
    });

    render(<CliCommandPreviewDrawer />);

    expect(screen.getByText('安全策略已拦截高危指令')).toBeInTheDocument();
    expect(screen.getByText('安全守卫阻断通知')).toBeInTheDocument();
    expect(screen.getByText(/高危操作拦截/)).toBeInTheDocument();
  });

  it('copies command output to clipboard', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('!! echo test');
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<CliCommandPreviewDrawer />);

    const copyBtn = screen.getByLabelText('复制命令输出');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalled();
    expect(screen.getByText('已复制')).toBeInTheDocument();
  });

  it('clears history on trash icon click', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('! ls');
    });

    const { rerender } = render(<CliCommandPreviewDrawer />);
    expect(screen.getByRole('region')).toBeInTheDocument();

    const clearBtn = screen.getByLabelText('清空执行记录');
    act(() => {
      fireEvent.click(clearBtn);
    });

    expect(useCliPassthroughStore.getState().history.length).toBe(0);
    rerender(<CliCommandPreviewDrawer />);
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('closes drawer on collapse button click', async () => {
    await act(async () => {
      await useCliPassthroughStore.getState().executeCommand('! pytest');
    });

    const onClose = vi.fn();
    render(<CliCommandPreviewDrawer onClose={onClose} />);

    const closeBtn = screen.getByLabelText('收起抽屉');
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(useCliPassthroughStore.getState().isDrawerOpen).toBe(false);
  });
});
