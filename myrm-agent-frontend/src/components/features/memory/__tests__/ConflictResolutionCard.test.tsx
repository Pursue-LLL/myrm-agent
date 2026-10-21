/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConflictResolutionCard } from '../cards/ConflictResolutionCard';
import type { MemoryCommandConflictItem } from '@/services/memory/commandCenter';

// The global test setup mocks next-intl so `t(key) === key`.
describe('ConflictResolutionCard', () => {
  const mockItem: MemoryCommandConflictItem = {
    id: 'conflict:conf-123',
    kind: 'pending_conflict',
    status: 'pending',
    memory_id: 'mem-1',
    related_memory_id: '',
    title: '工作地变动',
    description: '常驻深圳南山区 ⟷ 搬到西雅图生活办公',
    existing_content: '常驻深圳南山区',
    candidate_content: '搬到西雅图生活办公',
    created_at: '2026-09-04T12:00:00Z',
  };

  it('renders existing fact and candidate fact correctly', () => {
    render(<ConflictResolutionCard item={mockItem} />);

    expect(screen.getByText('工作地变动')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.conflictCardExisting')).toBeInTheDocument();
    expect(screen.getByText('常驻深圳南山区')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.conflictCardCandidate')).toBeInTheDocument();
    expect(screen.getByText('搬到西雅图生活办公')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.conflictCardPending')).toBeInTheDocument();
  });

  it('triggers onResolve callback when clicking arbitration buttons', async () => {
    const handleResolve = vi.fn().mockResolvedValue(undefined);
    render(<ConflictResolutionCard item={mockItem} onResolve={handleResolve} />);

    // Click keep_new
    const keepNewBtn = screen.getByText('commandCenter.conflictCardKeepNew');
    fireEvent.click(keepNewBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'keep_new');

    // Click keep_old
    const keepOldBtn = screen.getByText('commandCenter.conflictCardKeepOld');
    fireEvent.click(keepOldBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'keep_old');

    // Click coexist
    const coexistBtn = screen.getByText('commandCenter.conflictCardCoexist');
    fireEvent.click(coexistBtn);
    expect(handleResolve).toHaveBeenCalledWith('conflict:conf-123', 'coexist');
  });

  it('does not display arbitration buttons for already resolved conflicts', () => {
    const resolvedItem: MemoryCommandConflictItem = {
      ...mockItem,
      status: 'resolved',
    };
    render(<ConflictResolutionCard item={resolvedItem} onResolve={vi.fn()} />);

    expect(screen.queryByText('commandCenter.conflictCardKeepNew')).not.toBeInTheDocument();
    expect(screen.queryByText('commandCenter.conflictCardKeepOld')).not.toBeInTheDocument();
    expect(screen.queryByText('commandCenter.conflictCardCoexist')).not.toBeInTheDocument();
  });
});
