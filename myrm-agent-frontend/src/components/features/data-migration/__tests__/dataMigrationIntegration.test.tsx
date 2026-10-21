import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DataMigrationSection } from '../DataMigrationSection';
import { useDataMigrationStore } from '../useDataMigrationStore';
import { FourDimensionalAssets } from '../dataMigrationTypes';

describe('DataMigration Integration End-to-End', () => {
  beforeEach(() => {
    act(() => {
      useDataMigrationStore.getState().reset();
    });
  });

  it('完整走通：后台静默检测 -> 触发 Toast -> 打开对账单 -> 确认导入全流程', async () => {
    render(<DataMigrationSection />);

    // 1. 触发静默检测
    act(() => {
      useDataMigrationStore.getState().triggerSilentDetection('qoder_v1');
    });

    // 2. 检查 Toast 浮窗已出现
    expect(screen.getByTestId('migration-silent-toast')).toBeInTheDocument();
    expect(
      screen.getByText('已静默探测到历史智能体资产')
    ).toBeInTheDocument();

    // 3. 点击 Toast 中的“查看对账单”
    const viewReportToastBtn = screen.getByRole('button', {
      name: /查看对账单/i,
    });
    act(() => {
      fireEvent.click(viewReportToastBtn);
    });

    // 4. 对账单弹窗应已打开
    expect(
      screen.getByTestId('migration-reconciliation-modal')
    ).toBeInTheDocument();

    // 5. 切换合并策略为 "rename"
    const renameBtn = screen.getByRole('button', { name: /自动重命名/i });
    act(() => {
      fireEvent.click(renameBtn);
    });
    expect(useDataMigrationStore.getState().conflictStrategy).toBe('rename');

    // 6. 点击确认无损迁移导入
    const confirmBtn = screen.getByRole('button', {
      name: /确认无损迁移导入/i,
    });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    // 7. 弹窗和 Toast 均应关闭，数据写入完成，审计日志记录导入成功
    expect(
      screen.queryByTestId('migration-reconciliation-modal')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('migration-silent-toast')
    ).not.toBeInTheDocument();

    const finalStore = useDataMigrationStore.getState();
    expect(finalStore.existingFingerprints.size).toBeGreaterThan(0);
    expect(
      finalStore.logs.some((l) => l.message.includes('迁移对账完成'))
    ).toBe(true);
  });

  it('支持多次载入不同历史来源的资产并按指纹准确增量合并', () => {
    const store = useDataMigrationStore.getState();

    const assets1: FourDimensionalAssets = {
      tasks: [{ id: 't1', title: '任务一', createdAt: 1, status: 'completed' }],
      cronJobs: [
        {
          id: 'c1',
          name: '任务一巡检',
          cronExpression: '0 0 * * *',
          taskTemplate: 'daily',
          enabled: true,
        },
      ],
      memories: [
        {
          id: 'm1',
          category: 'project',
          content: '知识库一',
          confidence: 0.9,
          createdAt: 1,
        },
      ],
      mcpConfigs: [
        {
          name: 'sqlite-tools',
          transport: 'stdio',
          command: 'python',
          args: [],
          enabled: true,
        },
      ],
    };

    // 第一次载入并导入
    act(() => {
      store.loadIncomingData(assets1, 'qoder_v1', 'file1.json');
    });
    act(() => {
      store.executeImport();
    });

    expect(useDataMigrationStore.getState().existingFingerprints.size).toBe(4);

    // 第二次载入含有 1 个相同指纹（sqlite-tools）和 1 个新资产的数据
    const assets2: FourDimensionalAssets = {
      tasks: [{ id: 't2', title: '任务二', createdAt: 2, status: 'pending' }],
      cronJobs: [],
      memories: [],
      mcpConfigs: [
        {
          name: 'sqlite-tools', // 重复指纹
          transport: 'stdio',
          command: 'python3',
          args: ['--debug'],
          enabled: true,
        },
      ],
    };

    act(() => {
      useDataMigrationStore
        .getState()
        .loadIncomingData(assets2, 'hermes_legacy', 'file2.json');
    });

    const report = useDataMigrationStore.getState().activeReport;
    expect(report).not.toBeNull();
    expect(report?.mcpConfigs.duplicateCount).toBe(1);
    expect(report?.tasks.newCount).toBe(1);

    // 采用 skip 策略导入
    act(() => {
      useDataMigrationStore.getState().setConflictStrategy('skip');
    });
    const importedResult = act(() => {
      return useDataMigrationStore.getState().executeImport();
    });

    expect(importedResult).toBeDefined();
    // 任务增至 2 项，mcp 保持 1 项（重复项被跳过）
    expect(useDataMigrationStore.getState().existingFingerprints.has('task:任务二')).toBe(true);
  });

  it('Toast 浮窗支持点击关闭按钮直接静默关闭', () => {
    render(<DataMigrationSection />);

    // 触发静默检测并弹出 Toast
    act(() => {
      useDataMigrationStore.getState().triggerSilentDetection('openclaw');
    });

    expect(screen.getByTestId('migration-silent-toast')).toBeInTheDocument();

    const dismissBtn = screen.getByRole('button', { name: '关闭提示' });
    act(() => {
      fireEvent.click(dismissBtn);
    });

    expect(
      screen.queryByTestId('migration-silent-toast')
    ).not.toBeInTheDocument();
    expect(useDataMigrationStore.getState().showSilentToast).toBe(false);
  });
});
