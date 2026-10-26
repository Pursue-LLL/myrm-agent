/** @vitest-environment jsdom */

import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AppDialogHost from '@/components/features/app-shell/app-dialog-host';
import { useAppDialogStore } from '@/store/useAppDialogStore';
import { MemorySecondaryGovernanceToolbar } from '../MemorySecondaryGovernanceToolbar';
import { RecallCandidate } from '../recallSimulatorTypes';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    confidenceWeight: '置信度权重',
    mustAvoidTrap: '强负向避坑基因',
    normalGene: '普通正向经验',
    lockBtn: '锁定',
    unlockBtn: '解锁',
    disableBtn: '禁用',
    enableBtn: '启用',
    mergeDuplicateBtn: '合并相似项',
    mergePrompt: '请输入要合并的目标记忆 ID',
    confirm: '确认',
    cancel: '取消',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockCandidate: RecallCandidate = {
  memory_id: 'mem-test-01',
  content: '测试内存内容',
  summary: '测试摘要',
  recall_type: 'causal_gene',
  scores: {
    rrf_score: 0.9,
    bm25_score: 10.0,
    vector_similarity: 0.85,
    causal_relevance: 0.95,
  },
  confidence: 0.8,
  is_negative_trap: false,
  status: 'active',
  hit_reason: '测试命中',
  tags: ['Kernel'],
};

describe('MemorySecondaryGovernanceToolbar', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppDialogStore.setState({ current: null, open: false, queue: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders confidence slider with initial percentage', () => {
    render(<MemorySecondaryGovernanceToolbar candidate={mockCandidate} onUpdate={vi.fn()} />);

    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('普通正向经验')).toBeInTheDocument();
  });

  it('updates confidence slider value and triggers onUpdate on mouse up', async () => {
    const handleUpdate = vi.fn().mockResolvedValue(undefined);
    render(<MemorySecondaryGovernanceToolbar candidate={mockCandidate} onUpdate={handleUpdate} />);

    const slider = screen.getByLabelText('置信度权重:');
    fireEvent.change(slider, { target: { value: '0.95' } });
    expect(screen.getByText('95%')).toBeInTheDocument();

    await act(async () => {
      fireEvent.mouseUp(slider);
    });

    expect(handleUpdate).toHaveBeenCalledWith({ confidence: 0.95 });
  });

  it('toggles negative pitfall trap flag and calls onUpdate', async () => {
    const handleUpdate = vi.fn().mockResolvedValue(undefined);
    render(<MemorySecondaryGovernanceToolbar candidate={mockCandidate} onUpdate={handleUpdate} />);

    const trapBtn = screen.getByRole('button', { name: /普通正向经验/i });
    await act(async () => {
      fireEvent.click(trapBtn);
    });

    expect(handleUpdate).toHaveBeenCalledWith({ is_negative_trap: true });
    expect(screen.getByText('强负向避坑基因')).toBeInTheDocument();
  });

  it('toggles lock and disable lifecycle statuses', async () => {
    const handleUpdate = vi.fn().mockResolvedValue(undefined);
    render(<MemorySecondaryGovernanceToolbar candidate={mockCandidate} onUpdate={handleUpdate} />);

    // Click Lock
    const lockBtn = screen.getByRole('button', { name: '锁定' });
    await act(async () => {
      fireEvent.click(lockBtn);
    });
    expect(handleUpdate).toHaveBeenCalledWith({ status: 'locked' });

    // Click Disable
    const disableBtn = screen.getByRole('button', { name: '禁用' });
    await act(async () => {
      fireEvent.click(disableBtn);
    });
    expect(handleUpdate).toHaveBeenCalledWith({ status: 'disabled' });
  });

  describe('merging a duplicate', () => {
    const renderWithDialogs = (onUpdate: React.ComponentProps<typeof MemorySecondaryGovernanceToolbar>['onUpdate']) =>
      render(
        <>
          <MemorySecondaryGovernanceToolbar candidate={mockCandidate} onUpdate={onUpdate} />
          <AppDialogHost />
        </>,
      );

    it('asks for the target id in the app and merges into the id that was typed', async () => {
      const user = userEvent.setup();
      const handleUpdate = vi.fn().mockResolvedValue(undefined);
      renderWithDialogs(handleUpdate);

      fireEvent.click(screen.getByRole('button', { name: /合并相似项/i }));

      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveTextContent('请输入要合并的目标记忆 ID');
      await user.type(screen.getByRole('textbox'), '  mem-parent-99 ');
      await user.click(screen.getByRole('button', { name: '确认' }));

      await waitFor(() => expect(handleUpdate).toHaveBeenCalledWith({ status: 'disabled' }, 'mem-parent-99'));
    });

    it('changes nothing when the question is dismissed', async () => {
      const user = userEvent.setup();
      const handleUpdate = vi.fn().mockResolvedValue(undefined);
      renderWithDialogs(handleUpdate);

      fireEvent.click(screen.getByRole('button', { name: /合并相似项/i }));
      await user.type(await screen.findByRole('textbox'), 'mem-parent-99');
      await user.click(screen.getByRole('button', { name: '取消' }));

      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
      expect(handleUpdate).not.toHaveBeenCalled();
    });

    it('does not accept an empty target id', async () => {
      const handleUpdate = vi.fn().mockResolvedValue(undefined);
      renderWithDialogs(handleUpdate);

      fireEvent.click(screen.getByRole('button', { name: /合并相似项/i }));
      await screen.findByRole('alertdialog');

      expect(screen.getByRole('button', { name: '确认' })).toBeDisabled();
      expect(handleUpdate).not.toHaveBeenCalled();
    });
  });
});
