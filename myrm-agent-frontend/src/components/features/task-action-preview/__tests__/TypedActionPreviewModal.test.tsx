import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TypedActionPreviewModal } from '../TypedActionPreviewModal';
import type { TypedActionPayload } from '../taskActionPreviewTypes';

describe('TypedActionPreviewModal', () => {
  const mockLowRiskAction: TypedActionPayload = {
    actionId: 'act-001',
    category: 'goal_lifecycle',
    title: '暂停目标执行',
    description: '临时挂起当前运行中的长程目标，保留上下文检查点。',
    riskLevel: 'low',
    targetResourceId: 'goal-998',
    targetResourceName: '重构工作区',
    sideEffects: ['该目标下的子任务将暂停执行'],
    requiresExplicitConfirmation: false,
  };

  const mockCriticalAction: TypedActionPayload = {
    actionId: 'act-002',
    category: 'file_mutation',
    title: '批量清空配置表并重置数据库',
    description: '此操作将彻底删除所有持久化记录并回滚到初始模板。',
    riskLevel: 'critical',
    targetResourceId: 'db-main',
    targetResourceName: '主数据仓库',
    affectedFiles: ['src/config/db.json', 'data/sqlite.db'],
    quotaDelta: [
      { metric: 'storage_mb', before: 512, after: 0 },
      { metric: 'records', before: '14,200', after: '0' },
    ],
    sideEffects: ['所有未备份的数据将永久丢失', '所有活跃连接将被强制中断'],
    requiresExplicitConfirmation: true,
  };

  it('renders nothing when isOpen is false or action is null', () => {
    const { container: c1 } = render(
      <TypedActionPreviewModal
        action={mockLowRiskAction}
        isOpen={false}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <TypedActionPreviewModal
        action={null}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(c2.firstChild).toBeNull();
  });

  it('renders low risk modal and confirms without requiring checkboxes', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    render(
      <TypedActionPreviewModal
        action={mockLowRiskAction}
        isOpen={true}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText('暂停目标执行')).toBeDefined();
    expect(screen.getByText('低风险操作')).toBeDefined();
    expect(screen.getByText(/该目标下的子任务将暂停执行/)).toBeDefined();

    const confirmBtn = screen.getByRole('button', { name: /确认并下发执行/i });
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith(mockLowRiskAction);
  });

  it('enforces checkbox and CONFIRM keyword gate for critical actions', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    render(
      <TypedActionPreviewModal
        action={mockCriticalAction}
        isOpen={true}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText('CRITICAL · 危险不可逆')).toBeDefined();
    expect(screen.getByText(/src\/config\/db\.json/)).toBeDefined();
    expect(screen.getByText(/storage_mb/)).toBeDefined();

    const confirmBtn = screen.getByRole('button', { name: /确认并下发执行/i });
    // Initially disabled
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);

    // 1. Check the confirmation checkbox
    const checkbox = screen.getByRole('checkbox');
    fireEvent.click(checkbox);
    // Still disabled because keyword CONFIRM is not entered
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);

    // 2. Enter invalid keyword
    const input = screen.getByPlaceholderText('输入 CONFIRM');
    fireEvent.change(input, { target: { value: 'wrong' } });
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);

    // 3. Enter CONFIRM
    fireEvent.change(input, { target: { value: 'CONFIRM' } });
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith(mockCriticalAction);
  });

  it('handles cancel button click and escape key', () => {
    const onCancel = vi.fn();

    render(
      <TypedActionPreviewModal
        action={mockLowRiskAction}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    const cancelBtn = screen.getByRole('button', { name: '取消' });
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it('shows executing loading state and disables interaction', () => {
    render(
      <TypedActionPreviewModal
        action={mockLowRiskAction}
        isOpen={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        isExecuting={true}
      />,
    );

    expect(screen.getByText('正在下发并生成回执...')).toBeDefined();
    const cancelBtn = screen.getByRole('button', { name: '取消' });
    expect(cancelBtn.hasAttribute('disabled')).toBe(true);
  });
});
