import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MigrationReconciliationModal } from '../MigrationReconciliationModal';
import { useDataMigrationStore } from '../useDataMigrationStore';
import { FourDimensionalAssets } from '../dataMigrationTypes';

describe('MigrationReconciliationModal', () => {
  const sampleIncomingAssets: FourDimensionalAssets = {
    tasks: [
      {
        id: 'task-101',
        title: '测试历史任务',
        createdAt: Date.now(),
        status: 'completed',
      },
    ],
    cronJobs: [
      {
        id: 'cron-101',
        name: '每小时备份作业',
        cronExpression: '0 * * * *',
        taskTemplate: 'hourly_backup',
        enabled: true,
      },
    ],
    memories: [
      {
        id: 'mem-101',
        category: 'user_preference',
        content: '偏好深色模式与紧凑排版',
        confidence: 0.95,
        createdAt: Date.now(),
      },
    ],
    mcpConfigs: [
      {
        name: 'filesystem-server',
        transport: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-filesystem'],
        enabled: true,
      },
    ],
  };

  beforeEach(() => {
    act(() => {
      useDataMigrationStore.getState().reset();
    });
  });

  it('在未打开或无活跃对账报告时不渲染任何 DOM', () => {
    render(<MigrationReconciliationModal />);
    expect(
      screen.queryByTestId('migration-reconciliation-modal')
    ).not.toBeInTheDocument();
  });

  it('载入数据并打开弹窗后完整呈现对账单及四维资产统计', () => {
    act(() => {
      useDataMigrationStore
        .getState()
        .loadIncomingData(sampleIncomingAssets, 'qoder_v1', 'qoder_backup.json');
    });

    render(<MigrationReconciliationModal />);

    expect(
      screen.getByTestId('migration-reconciliation-modal')
    ).toBeInTheDocument();
    expect(screen.getByText('历史资产迁移对账单')).toBeInTheDocument();
    expect(screen.getByText(/老版 Qoder 工作台/)).toBeInTheDocument();

    // 4 维资产标题
    expect(screen.getByText(/历史任务记录 \(Tasks\)/)).toBeInTheDocument();
    expect(screen.getByText(/周期性作业 \(Cron Jobs\)/)).toBeInTheDocument();
    expect(screen.getByText(/长短期记忆 \(Memories\)/)).toBeInTheDocument();
    expect(screen.getByText(/MCP 外部服务 \(Tools\)/)).toBeInTheDocument();
  });

  it('支持切换重复项合并策略 (skip, overwrite, rename)', () => {
    act(() => {
      useDataMigrationStore
        .getState()
        .loadIncomingData(sampleIncomingAssets, 'qoder_v1', 'qoder_backup.json');
    });

    render(<MigrationReconciliationModal />);

    const skipBtn = screen.getByRole('button', { name: /跳过重复项/i });
    const overwriteBtn = screen.getByRole('button', { name: /覆盖现有项/i });
    const renameBtn = screen.getByRole('button', { name: /自动重命名/i });

    act(() => {
      fireEvent.click(overwriteBtn);
    });
    expect(useDataMigrationStore.getState().conflictStrategy).toBe('overwrite');

    act(() => {
      fireEvent.click(renameBtn);
    });
    expect(useDataMigrationStore.getState().conflictStrategy).toBe('rename');

    act(() => {
      fireEvent.click(skipBtn);
    });
    expect(useDataMigrationStore.getState().conflictStrategy).toBe('skip');
  });

  it('点击关闭按钮或取消按钮会关闭弹窗', () => {
    act(() => {
      useDataMigrationStore
        .getState()
        .loadIncomingData(sampleIncomingAssets, 'qoder_v1', 'qoder_backup.json');
    });

    render(<MigrationReconciliationModal />);

    const closeBtn = screen.getByRole('button', { name: '关闭对账单' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useDataMigrationStore.getState().isReconciliationModalOpen).toBe(
      false
    );
  });

  it('点击确认无损迁移导入按钮执行导入并合并资产', async () => {
    act(() => {
      useDataMigrationStore
        .getState()
        .loadIncomingData(sampleIncomingAssets, 'openclaw', 'openclaw_data.json');
    });

    render(<MigrationReconciliationModal />);

    const confirmBtn = screen.getByRole('button', {
      name: /确认无损迁移导入/i,
    });

    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    const store = useDataMigrationStore.getState();
    expect(store.isReconciliationModalOpen).toBe(false);
    expect(store.status).toBe('completed');
    expect(store.existingFingerprints.size).toBeGreaterThan(0);
    expect(store.logs.length).toBeGreaterThan(0);
  });
});
