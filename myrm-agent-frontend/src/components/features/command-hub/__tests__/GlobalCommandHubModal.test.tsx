import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { GlobalCommandHubModal } from '../GlobalCommandHubModal';
import { useGlobalCommandHubStore } from '../useGlobalCommandHubStore';

describe('GlobalCommandHubModal Component Suite', () => {
  beforeEach(() => {
    useGlobalCommandHubStore.getState().resetState();
  });

  it('renders nothing when command hub is closed', () => {
    const { container } = render(<GlobalCommandHubModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders command hub modal with search input, categories, and command list when open', () => {
    useGlobalCommandHubStore.getState().openHub();
    render(<GlobalCommandHubModal />);

    expect(screen.getByLabelText('全局 ⌘K 全能命令中枢')).toBeInTheDocument();
    expect(screen.getByLabelText('命令搜索输入框')).toBeInTheDocument();
    expect(screen.getByLabelText('命令类别筛选栏')).toBeInTheDocument();
    expect(screen.getByLabelText('命令匹配列表')).toBeInTheDocument();
    expect(screen.getByLabelText('键盘操作指引')).toBeInTheDocument();

    // 默认应包含各核心预设命令
    expect(screen.getByText('跳转：智能体名册矩阵')).toBeInTheDocument();
    expect(screen.getByText('派工：代码审查与重构专家')).toBeInTheDocument();
    expect(screen.getByText('Git：查看工作区状态 (git status)')).toBeInTheDocument();
  });

  it('filters command list by search query input', () => {
    useGlobalCommandHubStore.getState().openHub();
    render(<GlobalCommandHubModal />);

    const searchInput = screen.getByLabelText('命令搜索输入框');

    fireEvent.change(searchInput, { target: { value: '代码审查' } });

    expect(screen.getByText('派工：代码审查与重构专家')).toBeInTheDocument();
    expect(screen.queryByText('Git：查看工作区状态 (git status)')).not.toBeInTheDocument();
  });

  it('filters commands by clicking category filter buttons', () => {
    useGlobalCommandHubStore.getState().openHub();
    render(<GlobalCommandHubModal />);

    const gitFilterBtn = screen.getByRole('button', { name: '筛选 Git 运维' });
    fireEvent.click(gitFilterBtn);

    expect(useGlobalCommandHubStore.getState().activeCategory).toBe('git');
    expect(screen.getByText('Git：查看工作区状态 (git status)')).toBeInTheDocument();
    expect(screen.queryByText('跳转：智能体名册矩阵')).not.toBeInTheDocument();
  });

  it('executes command and closes modal on item click', () => {
    const mockAction = vi.fn();
    useGlobalCommandHubStore.getState().registerCommand({
      id: 'mock-cmd-run',
      category: 'action',
      title: '一键执行自动化巡检',
      iconName: 'Zap',
      keywords: ['test'],
      action: mockAction,
    });

    useGlobalCommandHubStore.getState().openHub();
    render(<GlobalCommandHubModal />);

    const item = screen.getByText('一键执行自动化巡检');
    fireEvent.click(item);

    expect(mockAction).toHaveBeenCalledTimes(1);
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);
  });

  it('closes command hub on close button click and responds to Escape key', () => {
    useGlobalCommandHubStore.getState().openHub();
    render(<GlobalCommandHubModal />);

    const closeBtn = screen.getByRole('button', { name: '关闭命令面板' });
    fireEvent.click(closeBtn);

    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);

    // 重新打开并通过 Escape 键测试关闭
    act(() => {
      useGlobalCommandHubStore.getState().openHub();
    });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);
  });

  it('toggles command hub via ⌘K keyboard shortcut', () => {
    render(<GlobalCommandHubModal />);

    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);

    // 模拟按下 ⌘K
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(true);

    // 再次按下 ⌘K 关闭
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(useGlobalCommandHubStore.getState().isOpen).toBe(false);
  });
});
