import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkspaceScopeSwitcher } from '../WorkspaceScopeSwitcher';
import { useWorkspaceScopeStore } from '../useWorkspaceScopeStore';

describe('WorkspaceScopeSwitcher Component', () => {
  beforeEach(() => {
    useWorkspaceScopeStore.getState().resetState();
  });

  it('renders default personal scope badge and closed dropdown', () => {
    render(<WorkspaceScopeSwitcher />);

    expect(screen.getByText('个人私有空间')).toBeInTheDocument();
    expect(screen.getByText('本地沙箱')).toBeInTheDocument();
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens dropdown and displays personal option and teams list', () => {
    render(<WorkspaceScopeSwitcher />);

    const triggerButton = screen.getByRole('button', { name: /个人私有空间/ });
    fireEvent.click(triggerButton);

    const menu = screen.getByRole('menu');
    expect(menu).toBeInTheDocument();

    expect(screen.getByText('独立安全环境')).toBeInTheDocument();
    expect(screen.getByText('团队协同空间 (Control Plane)')).toBeInTheDocument();
    expect(screen.getByText('Acme AI Engineering')).toBeInTheDocument();
    expect(screen.getByText('Open Labs Research')).toBeInTheDocument();
    expect(screen.getByText('Zero-Leak 硬隔离看门狗已生效')).toBeInTheDocument();
  });

  it('switches between personal and team workspaces with isolation audit', () => {
    render(<WorkspaceScopeSwitcher />);

    // 打开下拉菜单
    const triggerButton = screen.getByRole('button', { name: /个人私有空间/ });
    fireEvent.click(triggerButton);

    // 选中 Acme AI Engineering 团队
    const teamOption = screen.getByText('Acme AI Engineering');
    fireEvent.click(teamOption);

    // 状态更新为团队空间
    expect(useWorkspaceScopeStore.getState().currentScope).toBe('team');
    expect(useWorkspaceScopeStore.getState().activeTeamId).toBe('team-acme-corp');
    expect(useWorkspaceScopeStore.getState().lastIsolationAudit?.activeSessionPurged).toBe(true);
    expect(useWorkspaceScopeStore.getState().lastIsolationAudit?.localSecretKeysHidden).toBe(true);

    // 再次打开并切回个人私有工作空间
    const teamTrigger = screen.getByRole('button', { name: /Acme AI Engineering/ });
    fireEvent.click(teamTrigger);

    const personalOption = screen.getByText('个人私有工作空间');
    fireEvent.click(personalOption);

    expect(useWorkspaceScopeStore.getState().currentScope).toBe('personal');
    expect(useWorkspaceScopeStore.getState().lastIsolationAudit?.localSecretKeysHidden).toBe(false);
  });
});
