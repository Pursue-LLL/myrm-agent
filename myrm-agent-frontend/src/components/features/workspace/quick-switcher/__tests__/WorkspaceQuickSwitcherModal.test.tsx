import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkspaceQuickSwitcherModal } from '../WorkspaceQuickSwitcherModal';
import { useWorkspaceQuickSwitcherStore } from '../useWorkspaceQuickSwitcherStore';

describe('WorkspaceQuickSwitcherModal', () => {
  beforeEach(() => {
    useWorkspaceQuickSwitcherStore.getState().resetToDefaults();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<WorkspaceQuickSwitcherModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog and search input when opened', () => {
    useWorkspaceQuickSwitcherStore.getState().openSwitcher();
    render(<WorkspaceQuickSwitcherModal />);

    const dialog = screen.getByRole('dialog', { name: '全局工作区快速切换器' });
    expect(dialog).toBeInTheDocument();

    const searchInput = screen.getByLabelText('搜索工作区');
    expect(searchInput).toBeInTheDocument();

    const rows = screen.getAllByTestId('workspace-palette-row');
    expect(rows.length).toBeGreaterThanOrEqual(3);
  });

  it('filters workspace items by typing into search box', () => {
    useWorkspaceQuickSwitcherStore.getState().openSwitcher();
    render(<WorkspaceQuickSwitcherModal />);

    const searchInput = screen.getByLabelText('搜索工作区');
    fireEvent.change(searchInput, { target: { value: 'frontend' } });

    const rows = screen.getAllByTestId('workspace-palette-row');
    expect(rows.length).toBe(1);
    expect(screen.getByText('myrm-agent-frontend')).toBeInTheDocument();
  });

  it('switches workspace when a row is clicked', () => {
    useWorkspaceQuickSwitcherStore.getState().openSwitcher();
    render(<WorkspaceQuickSwitcherModal />);

    const targetRow = screen.getByText('myrm-agent-frontend');
    fireEvent.click(targetRow);

    const state = useWorkspaceQuickSwitcherStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.currentWorkspaceId).toBe('ws-frontend-app');
  });

  it('switches tabs between All, Recent, and Favorites', () => {
    useWorkspaceQuickSwitcherStore.getState().openSwitcher();
    render(<WorkspaceQuickSwitcherModal />);

    const favTab = screen.getByRole('button', { name: /星标收藏/ });
    fireEvent.click(favTab);

    const storeState = useWorkspaceQuickSwitcherStore.getState();
    expect(storeState.activeTab).toBe('favorites');
  });

  it('toggles add local workspace form and creates new workspace', () => {
    useWorkspaceQuickSwitcherStore.getState().openSwitcher();
    render(<WorkspaceQuickSwitcherModal />);

    const toggleAddBtn = screen.getByRole('button', { name: '添加本地工作区' });
    fireEvent.click(toggleAddBtn);

    expect(screen.getByText('注册新本地项目空间')).toBeInTheDocument();

    const nameInput = screen.getByLabelText('项目空间标识名称');
    const pathInput = screen.getByLabelText('本地绝对路径');

    fireEvent.change(nameInput, { target: { value: 'ai-analytics-hub' } });
    fireEvent.change(pathInput, { target: { value: '/Users/test/ai-analytics' } });

    const submitBtn = screen.getByRole('button', { name: '确认添加并切换' });
    fireEvent.click(submitBtn);

    const storeState = useWorkspaceQuickSwitcherStore.getState();
    expect(storeState.isOpen).toBe(false);
    expect(storeState.workspaces.some((w) => w.name === 'ai-analytics-hub')).toBe(true);
  });
});
