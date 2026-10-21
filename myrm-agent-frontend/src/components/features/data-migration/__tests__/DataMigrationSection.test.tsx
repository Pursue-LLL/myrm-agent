import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { DataMigrationSection } from '../DataMigrationSection';
import { useDataMigrationStore } from '../useDataMigrationStore';

describe('DataMigrationSection', () => {
  beforeEach(() => {
    act(() => {
      useDataMigrationStore.getState().reset();
    });
  });

  it('正确渲染标题、说明与三大预置来源导入卡片', () => {
    render(<DataMigrationSection />);

    expect(screen.getByTestId('data-migration-section')).toBeInTheDocument();
    expect(
      screen.getByText('数据导入与历史资产无损迁移')
    ).toBeInTheDocument();
    expect(
      screen.getByText('老版 Qoder 工作台')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Hermes 历史环境')
    ).toBeInTheDocument();
    expect(
      screen.getByText('OpenClaw Agent')
    ).toBeInTheDocument();
    expect(
      screen.getByText('自定义 SQLite / JSON 数据包导入')
    ).toBeInTheDocument();
  });

  it('允许切换自动静默巡检与导入开关', () => {
    render(<DataMigrationSection />);

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    expect(useDataMigrationStore.getState().autoSilentImportEnabled).toBe(false);

    fireEvent.click(checkbox);
    expect(useDataMigrationStore.getState().autoSilentImportEnabled).toBe(true);
  });

  it('点击立即执行后台静默扫描能够触发扫描并在成功后产生日志', async () => {
    render(<DataMigrationSection />);

    const scanBtn = screen.getByRole('button', {
      name: /立即执行后台静默扫描/i,
    });
    expect(scanBtn).toBeEnabled();

    await act(async () => {
      fireEvent.click(scanBtn);
    });

    const store = useDataMigrationStore.getState();
    expect(store.status).toBe('idle');
    expect(store.logs.length).toBeGreaterThan(0);
  });

  it('点击预置来源卡片的载入并对账能够载入数据并打开对账单弹窗', () => {
    render(<DataMigrationSection />);

    const loadButtons = screen.getAllByRole('button', {
      name: /载入并对账/i,
    });
    expect(loadButtons.length).toBe(3);

    // 点击第 1 个 (qoder_v1)
    act(() => {
      fireEvent.click(loadButtons[0]);
    });

    const store = useDataMigrationStore.getState();
    expect(store.activeReport).not.toBeNull();
    expect(store.isReconciliationModalOpen).toBe(true);
    expect(store.activeReport?.sourceType).toBe('qoder_v1');

    // 弹窗应该被渲染并出现在页面上
    expect(
      screen.getByTestId('migration-reconciliation-modal')
    ).toBeInTheDocument();
  });

  it('有日志产生时展示数据迁移审计日志区域，并可触发查看当前对账单', () => {
    act(() => {
      useDataMigrationStore.getState().loadIncomingData(
        {
          tasks: [],
          cronJobs: [],
          memories: [],
          mcpConfigs: [],
        },
        'hermes_legacy',
        '~/.hermes/backup.json'
      );
    });

    render(<DataMigrationSection />);

    expect(screen.getByText(/数据迁移审计日志/)).toBeInTheDocument();
    const viewReportBtn = screen.getByRole('button', {
      name: /查看当前对账单/i,
    });
    expect(viewReportBtn).toBeInTheDocument();

    act(() => {
      fireEvent.click(viewReportBtn);
    });

    expect(useDataMigrationStore.getState().isReconciliationModalOpen).toBe(
      true
    );
  });
});
