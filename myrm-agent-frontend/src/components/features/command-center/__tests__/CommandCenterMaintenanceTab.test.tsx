import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CommandCenterMaintenanceTab } from '../CommandCenterMaintenanceTab';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('CommandCenterMaintenanceTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandCenterStore.getState().resetStore();
  });

  it('应正确渲染 6 类维护动作卡片', () => {
    render(<CommandCenterMaintenanceTab />);

    expect(screen.getByTestId('command-center-maintenance-tab')).toBeInTheDocument();
    expect(screen.getByText(/一键运行 Doctor 诊断/)).toBeInTheDocument();
    expect(screen.getByText(/系统安全合规审计/)).toBeInTheDocument();
    expect(screen.getByText(/创建 SQLite\/Volume 备份/)).toBeInTheDocument();
    expect(screen.getByText(/生成 Debug Share 排障包/)).toBeInTheDocument();
    expect(screen.getByText(/Skill Curator 依赖体检/)).toBeInTheDocument();
    expect(screen.getByText(/记忆切片整理与压缩/)).toBeInTheDocument();
  });

  it('点击立即执行按钮能触发任务执行并呈现完成反馈', async () => {
    render(<CommandCenterMaintenanceTab />);

    const runButtons = screen.getAllByRole('button', { name: /立即执行/i });
    expect(runButtons.length).toBeGreaterThanOrEqual(1);

    fireEvent.click(runButtons[0]);

    expect(screen.getByTestId('maintenance-task-status')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/执行完毕，健康状态已确认/)).toBeInTheDocument();
    });
  });

  it('执行 Debug Share 能生成脱敏包预览并支持复制', () => {
    render(<CommandCenterMaintenanceTab />);

    const debugShareBtn = screen
      .getAllByRole('button', { name: /立即执行/i })
      .find((_, idx) => idx === 3);

    if (debugShareBtn) {
      fireEvent.click(debugShareBtn);
    }

    expect(screen.getByText(/Debug Share 脱敏排障包已生成/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /复制脱敏包/i })).toBeInTheDocument();
  });
});
