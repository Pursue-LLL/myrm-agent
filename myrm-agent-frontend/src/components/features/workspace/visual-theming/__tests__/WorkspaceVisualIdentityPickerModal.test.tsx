import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { WorkspaceVisualIdentityPickerModal } from '../WorkspaceVisualIdentityPickerModal';
import { useWorkspaceThemingStore } from '../useWorkspaceThemingStore';

describe('WorkspaceVisualIdentityPickerModal', () => {
  beforeEach(() => {
    useWorkspaceThemingStore.getState().reset();
  });

  it('renders nothing when isCustomizeThemeModalOpen is false', () => {
    const { container } = render(<WorkspaceVisualIdentityPickerModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with workspace details and identity pickers', () => {
    useWorkspaceThemingStore.getState().openCustomizeThemeModal('ws-core-dev');
    render(<WorkspaceVisualIdentityPickerModal />);

    expect(
      screen.getByTestId('workspace-theming-modal'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('工作区专属视觉标识定制'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('1. 选择工作区语义图标'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('2. 选择 Tailwind 主题色彩'),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue('系统研发')).toBeInTheDocument();
  });

  it('updates selected icon, color, label and saves theme', () => {
    const handleSaved = vi.fn();
    useWorkspaceThemingStore.getState().openCustomizeThemeModal('ws-core-dev');
    render(<WorkspaceVisualIdentityPickerModal onSaved={handleSaved} />);

    // 选择图标：商业企划
    const briefcaseIconBtn = screen.getByRole('button', {
      name: /商业企划/,
    });
    act(() => {
      fireEvent.click(briefcaseIconBtn);
    });

    // 选择颜色：翡翠绿
    const emeraldColorBtn = screen.getByRole('button', {
      name: '选择翡翠绿色',
    });
    act(() => {
      fireEvent.click(emeraldColorBtn);
    });

    // 修改标签
    const labelInput = screen.getByLabelText(/3. 专属角标文字/);
    act(() => {
      fireEvent.change(labelInput, { target: { value: '核心架构' } });
    });

    // 点击保存
    const saveBtn = screen.getByRole('button', {
      name: '保存并应用主题',
    });
    act(() => {
      fireEvent.click(saveBtn);
    });

    expect(handleSaved).toHaveBeenCalledTimes(1);
    expect(handleSaved).toHaveBeenCalledWith({
      icon: 'briefcase',
      color: 'emerald',
      customLabel: '核心架构',
    });

    const updatedWorkspace =
      useWorkspaceThemingStore.getState().workspaces['ws-core-dev'];
    expect(updatedWorkspace?.theme.icon).toBe('briefcase');
    expect(updatedWorkspace?.theme.color).toBe('emerald');
    expect(updatedWorkspace?.theme.customLabel).toBe('核心架构');
    expect(
      useWorkspaceThemingStore.getState().isCustomizeThemeModalOpen,
    ).toBe(false);
  });

  it('closes modal on Escape key press', () => {
    useWorkspaceThemingStore.getState().openCustomizeThemeModal('ws-core-dev');
    render(<WorkspaceVisualIdentityPickerModal />);

    expect(
      screen.getByTestId('workspace-theming-modal'),
    ).toBeInTheDocument();

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    expect(
      useWorkspaceThemingStore.getState().isCustomizeThemeModalOpen,
    ).toBe(false);
  });
});
