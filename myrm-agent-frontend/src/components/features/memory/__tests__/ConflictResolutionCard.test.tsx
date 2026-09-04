/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConflictResolutionCard } from '../cards/ConflictResolutionCard';
import type { MemoryCommandConflictItem } from '@/services/memory/commandCenter';

describe('ConflictResolutionCard', () => {
  const mockItem: MemoryCommandConflictItem = {
    id: 'conflict:conf-123',
    kind: 'pending_conflict',
    status: 'pending',
    memory_id: 'mem-1',
    related_memory_id: 'mem-2',
    title: '工作地变动',
    description: '当前认知：常驻深圳南山区 ⟷ 最新陈述：搬到西雅图生活办公',
    created_at: '2026-09-04T12:00:00Z',
  };

  it('renders existing fact and candidate fact correctly', () => {
    render(<ConflictResolutionCard item={mockItem} />);

    expect(screen.getByText('工作地变动')).toBeInTheDocument();
    expect(screen.getByText('当前已有记录')).toBeInTheDocument();
    expect(screen.getByText('常驻深圳南山区')).toBeInTheDocument();
    expect(screen.getByText('最新提及内容')).toBeInTheDocument();
    expect(screen.getByText('搬到西雅图生活办公')).toBeInTheDocument();
    expect(screen.getByText('待确认')).toBeInTheDocument();
  });

  it('triggers onResolve callback when clicking arbitration buttons', async () => {
    const handleResolve = vi.fn().mockResolvedValue(undefined);
    render(<ConflictResolutionCard item={mockItem} onResolve={handleResolve} />);

    // Click keep_new
    const keepNewBtn = screen.getByText('采纳最新事实');
    fireEvent.click(keepNewBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'keep_new');

    // Click keep_old
    const keepOldBtn = screen.getByText('保留原记录');
    fireEvent.click(keepOldBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'keep_old');

    // Click coexist
    const coexistBtn = screen.getByText('条件共存');
    fireEvent.click(coexistBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'coexist');
  });

  it('does not display arbitration buttons for already resolved conflicts', () => {
    const resolvedItem: MemoryCommandConflictItem = {
      ...mockItem,
      status: 'resolved',
    };
    render(<ConflictResolutionCard item={resolvedItem} onResolve={vi.fn()} />);

    expect(screen.queryByText('采纳最新事实')).not.toBeInTheDocument();
    expect(screen.queryByText('保留原记录')).not.toBeInTheDocument();
    expect(screen.queryByText('条件共存')).not.toBeInTheDocument();
  });
});
