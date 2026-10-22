import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataMigrationCenterModal } from '../DataMigrationCenterModal';
import { useDesktopPetPulseStore } from '../useDesktopPetPulseStore';

describe('DataMigrationCenterModal', () => {
  beforeEach(() => {
    useDesktopPetPulseStore.getState().resetAll();
  });

  it('当未打开弹窗时不渲染任何内容', () => {
    useDesktopPetPulseStore.setState({ isMigrationModalOpen: false });
    const { container } = render(<DataMigrationCenterModal />);
    expect(container.firstChild).toBeNull();
  });

  it('激活时渲染迁移中心、类别选项与策略选择器', () => {
    useDesktopPetPulseStore.setState({ isMigrationModalOpen: true });
    render(<DataMigrationCenterModal />);

    expect(
      screen.getByTestId('data-migration-center-modal')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('category-checkbox-tasks')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('category-checkbox-crons')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('migration-strategy-select')
    ).toBeInTheDocument();
    expect(screen.getByTestId('auto-detect-import-btn')).toBeInTheDocument();
  });

  it('支持切换数据类别勾选与合并策略', () => {
    useDesktopPetPulseStore.setState({ isMigrationModalOpen: true });
    render(<DataMigrationCenterModal />);

    const tasksCheckbox = screen.getByTestId(
      'category-checkbox-tasks'
    ) as HTMLInputElement;
    expect(tasksCheckbox.checked).toBe(true);

    fireEvent.click(tasksCheckbox);
    expect(tasksCheckbox.checked).toBe(false);

    const select = screen.getByTestId(
      'migration-strategy-select'
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'overwrite' } });
    expect(select.value).toBe('overwrite');
  });

  it('点击自动探测并导入，成功触发迁移并展示结果摘要', () => {
    const handleComplete = vi.fn();
    useDesktopPetPulseStore.setState({ isMigrationModalOpen: true });
    render(<DataMigrationCenterModal onMigrationComplete={handleComplete} />);

    const autoBtn = screen.getByTestId('auto-detect-import-btn');
    fireEvent.click(autoBtn);

    expect(handleComplete).toHaveBeenCalledTimes(1);
    expect(
      screen.getByTestId('migration-report-summary')
    ).toBeInTheDocument();
    expect(
      useDesktopPetPulseStore.getState().lastMigrationReport
    ).not.toBeNull();
  });

  it('点击关闭按钮收起弹窗', () => {
    const handleClose = vi.fn();
    useDesktopPetPulseStore.setState({ isMigrationModalOpen: true });
    render(<DataMigrationCenterModal onClose={handleClose} />);

    const closeBtn = screen.getByTestId('close-migration-modal-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(
      useDesktopPetPulseStore.getState().isMigrationModalOpen
    ).toBe(false);
  });
});
