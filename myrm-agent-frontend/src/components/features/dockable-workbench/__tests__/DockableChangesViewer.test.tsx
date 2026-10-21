import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DockableChangesViewer } from '../DockableChangesViewer';
import { useDockableWorkbenchStore } from '../useDockableWorkbenchStore';

describe('DockableChangesViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDockableWorkbenchStore.getState().resetStore();
  });

  it('观察面板应正确渲染变更文件计数、增删统计与文件列表', () => {
    render(<DockableChangesViewer />);

    expect(screen.getByText(/沙箱代码变更（Changes 只读观察）/)).toBeInTheDocument();
    expect(screen.getByText(/3 个文件/)).toBeInTheDocument();
    expect(screen.getAllByText(/runtimePolicy\.ts/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/apiGateway\.ts/i).length).toBeGreaterThanOrEqual(1);
  });

  it('点击左侧文件列表项能切换右侧选中的 Diff 内容', () => {
    render(<DockableChangesViewer />);

    const secondFileBtn = screen.getByRole('button', { name: /apiGateway\.ts/i });
    fireEvent.click(secondFileBtn);

    expect(screen.getAllByText(/apiGateway\.ts/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/RETRY_ATTEMPTS = 3/)).toBeInTheDocument();
  });

  it('点击在 GitHub 提 PR 按钮能触发 onCreatePR 回调', () => {
    const handlePR = vi.fn();
    render(<DockableChangesViewer onCreatePR={handlePR} />);

    const prBtn = screen.getByRole('button', { name: /在 GitHub 提 PR/i });
    fireEvent.click(prBtn);

    expect(handlePR).toHaveBeenCalledTimes(1);
  });

  it('应声明架构克制边界说明', () => {
    render(<DockableChangesViewer />);
    expect(
      screen.getByText(/架构克制：本面板仅提供轻量代码核验与审查，严禁手动增删文件/i)
    ).toBeInTheDocument();
  });
});
