import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DestructiveUndoCard } from '../DestructiveUndoCard';

const stableT = (key: string) => {
  const dict: Record<string, string> = {
    title: '破坏性操作已执行',
    description: '工作区已发生重大变更。已为您创建安全影子快照，支持限时无损回滚。',
    rollbackButton: '一键撤销并回滚快照',
    rollbackSuccess: '工作区已成功回滚至破坏前状态',
    rollbackFailed: '回滚快照失败，请检查工作区状态',
  };
  return dict[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('DestructiveUndoCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders undo card with countdown, snapshot id and triggers rollback api', async () => {
    const mockRollbackSuccess = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'rolled_back', snapshot_id: 'snap123456789' }),
    });
    global.fetch = fetchMock;

    render(
      <DestructiveUndoCard
        approvalId="app_123"
        snapshotId="snap123456789abcdef"
        onRollbackSuccess={mockRollbackSuccess}
      />
    );

    expect(screen.getByText('破坏性操作已执行')).toBeDefined();
    expect(screen.getByText(/快照指针: snap123456789/)).toBeDefined();
    expect(screen.getByText('一键撤销并回滚快照')).toBeDefined();

    const rollbackBtn = screen.getByText('一键撤销并回滚快照');
    fireEvent.click(rollbackBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/approvals/app_123/rollback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      expect(mockRollbackSuccess).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('工作区已成功回滚至破坏前状态')).toBeDefined();
  });
});
