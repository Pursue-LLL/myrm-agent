import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LocalProjectWorkspaceCard } from '../LocalProjectWorkspaceCard';
import { useArenaStore } from '../useArenaStore';

describe('LocalProjectWorkspaceCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useArenaStore.getState().resetStore();
  });

  it('未绑定状态下应渲染表单输入项', () => {
    render(<LocalProjectWorkspaceCard />);

    expect(screen.getByText('本地物理工作区与数据主权')).toBeInTheDocument();
    expect(screen.getByLabelText('项目显示名称')).toBeInTheDocument();
    expect(screen.getByLabelText('宿主机物理绝对路径')).toBeInTheDocument();
  });

  it('提交非法路径时应展示错误提示', () => {
    render(<LocalProjectWorkspaceCard />);

    const pathInput = screen.getByLabelText('宿主机物理绝对路径');
    fireEvent.change(pathInput, { target: { value: '../relative-path' } });

    const submitBtn = screen.getByRole('button', { name: /立即绑定本地物理工作区/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/路径不合法/)).toBeInTheDocument();
    expect(useArenaStore.getState().localProject).toBeNull();
  });

  it('提交合法绝对路径应成功绑定并切换视图', () => {
    render(<LocalProjectWorkspaceCard />);

    const nameInput = screen.getByLabelText('项目显示名称');
    const pathInput = screen.getByLabelText('宿主机物理绝对路径');
    fireEvent.change(nameInput, { target: { value: '我的核心系统' } });
    fireEvent.change(pathInput, { target: { value: '~/projects/core-system' } });

    const submitBtn = screen.getByRole('button', { name: /立即绑定本地物理工作区/i });
    fireEvent.click(submitBtn);

    expect(useArenaStore.getState().localProject?.isBound).toBe(true);
    expect(screen.getByText('我的核心系统')).toBeInTheDocument();
    expect(screen.getByText('本地优先离线可用')).toBeInTheDocument();
  });

  it('已绑定状态下点击解除目录绑定应清除绑定信息', () => {
    useArenaStore.getState().bindLocalProject('/Users/dev/code', '测试工作区');
    render(<LocalProjectWorkspaceCard />);

    expect(screen.getByText('测试工作区')).toBeInTheDocument();
    const unbindBtn = screen.getByRole('button', { name: '解除目录绑定' });
    fireEvent.click(unbindBtn);

    expect(useArenaStore.getState().localProject).toBeNull();
  });
});
