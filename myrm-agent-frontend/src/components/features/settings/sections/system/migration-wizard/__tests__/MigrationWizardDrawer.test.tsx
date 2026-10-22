import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MigrationWizardDrawer } from '../MigrationWizardDrawer';
import { useMigrationWizardStore } from '../useMigrationWizardStore';

describe('MigrationWizardDrawer Component', () => {
  beforeEach(() => {
    useMigrationWizardStore.getState().resetState();
  });

  it('renders nothing when drawer is closed', () => {
    const { container } = render(<MigrationWizardDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders detected ecosystem assets when drawer is opened', () => {
    useMigrationWizardStore.getState().openDrawer();
    render(<MigrationWizardDrawer />);

    expect(screen.getByText('本地生态免 SSH 零摩擦迁移向导')).toBeInTheDocument();
    expect(screen.getByText('OpenClaw Tech Lead')).toBeInTheDocument();
    expect(screen.getByText('Hermes Data Analyst')).toBeInTheDocument();
    expect(screen.getByText('Cursor Refactoring Bot')).toBeInTheDocument();
    expect(screen.getByText('git-commit-helper')).toBeInTheDocument();
    expect(screen.getByText('wechat-group-reporter')).toBeInTheDocument();
    expect(screen.getByText('github-mcp-server')).toBeInTheDocument();
    expect(screen.getByText('立即一键无损迁移')).toBeInTheDocument();
  });

  it('handles asset toggling and bulk selection actions', () => {
    useMigrationWizardStore.getState().openDrawer();
    render(<MigrationWizardDrawer />);

    const deselectAllBtn = screen.getByRole('button', { name: '取消全选' });
    fireEvent.click(deselectAllBtn);

    expect(screen.getByText('已勾选 0 项待迁移资产')).toBeInTheDocument();

    const selectAllBtn = screen.getByRole('button', { name: '全选' });
    fireEvent.click(selectAllBtn);

    expect(screen.getByText('已勾选 8 项待迁移资产')).toBeInTheDocument();
  });

  it('executes migration flow and displays completion screen', async () => {
    useMigrationWizardStore.getState().openDrawer();
    render(<MigrationWizardDrawer />);

    const migrateBtn = screen.getByRole('button', { name: /立即一键无损迁移/ });
    fireEvent.click(migrateBtn);

    await waitFor(() => {
      expect(screen.getByText('迁移完成！资产已全量就绪')).toBeInTheDocument();
    });

    expect(screen.getByText(/8 项生态资产/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /进入工作台体验/ })).toBeInTheDocument();
  });
});
