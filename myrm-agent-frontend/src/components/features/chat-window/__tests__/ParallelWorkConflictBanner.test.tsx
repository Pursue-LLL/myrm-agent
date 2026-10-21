'use client';

/**
 * [INPUT]: ParallelWorkConflictBanner.tsx 与 mock 冲突数据
 * [OUTPUT]: 验证并行工作冲突横幅渲染、并列对比、折叠展开与四大对账解决 CTA 触发
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/ParallelWorkConflictBanner.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  ParallelWorkConflictBanner,
  WorkConflictItem,
} from '../ParallelWorkConflictBanner';

const mockConflicts: WorkConflictItem[] = [
  {
    conflictId: 'conf-sess-01',
    sessionId: 'sess-test-01',
    resourceId: 'src/database/client.py',
    mutationType: 'file',
    workerA: {
      workerId: 'worker-sql-expert',
      resourceId: 'src/database/client.py',
      mutationType: 'file',
      contentHash: 'hash-abc123456',
      summary: 'Migrated connection pool to asyncpg',
    },
    workerB: {
      workerId: 'worker-sqlite-dev',
      resourceId: 'src/database/client.py',
      mutationType: 'file',
      contentHash: 'hash-def987654',
      summary: 'Added SQLite fallback for in-memory testing',
    },
    status: 'conflict_pending',
  },
  {
    conflictId: 'conf-sess-02',
    sessionId: 'sess-test-01',
    resourceId: 'config/app_settings.json',
    mutationType: 'config',
    workerA: {
      workerId: 'worker-auth',
      resourceId: 'config/app_settings.json',
      mutationType: 'config',
      contentHash: 'hash-conf-auth',
      summary: 'Enabled OIDC auth flags',
    },
    workerB: {
      workerId: 'worker-perf',
      resourceId: 'config/app_settings.json',
      mutationType: 'config',
      contentHash: 'hash-conf-perf',
      summary: 'Increased concurrency limit to 20',
    },
    status: 'conflict_pending',
  },
];

describe('ParallelWorkConflictBanner', () => {
  it('returns null when no conflicts or all are resolved', () => {
    const { container: c1 } = render(<ParallelWorkConflictBanner conflicts={[]} />);
    expect(c1).toBeEmptyDOMElement();

    const resolvedConflicts: WorkConflictItem[] = [
      {
        ...mockConflicts[0],
        status: 'resolved',
      },
    ];
    const { container: c2 } = render(<ParallelWorkConflictBanner conflicts={resolvedConflicts} />);
    expect(c2).toBeEmptyDOMElement();
  });

  it('renders banner header with conflict count badge and Fail-Closed alert', () => {
    render(<ParallelWorkConflictBanner conflicts={mockConflicts} />);

    expect(screen.getByTestId('parallel-work-conflict-banner')).toBeInTheDocument();
    expect(screen.getByText('多 Bot 并行冲突拦截门 (Reconciliation Gate)')).toBeInTheDocument();
    expect(screen.getByTestId('conflict-count-badge')).toHaveTextContent('2 处冲突待对账');
    expect(screen.getByText('Fail-Closed 拦截自动合并')).toBeInTheDocument();
  });

  it('renders conflict items, resources and side-by-side worker proposals', () => {
    render(<ParallelWorkConflictBanner conflicts={mockConflicts} />);

    expect(screen.getByText('src/database/client.py')).toBeInTheDocument();
    expect(screen.getByText('config/app_settings.json')).toBeInTheDocument();

    // The first item is expanded by default
    expect(screen.getByText('Worker A: worker-sql-expert')).toBeInTheDocument();
    expect(screen.getByText('Migrated connection pool to asyncpg')).toBeInTheDocument();
    expect(screen.getByText('Worker B: worker-sqlite-dev')).toBeInTheDocument();
    expect(screen.getByText('Added SQLite fallback for in-memory testing')).toBeInTheDocument();
  });

  it('triggers reconciliation actions: keep A, keep B, three-way merge, abort', () => {
    const onResolve = vi.fn();
    render(
      <ParallelWorkConflictBanner
        conflicts={mockConflicts}
        onResolveConflict={onResolve}
      />
    );

    // Keep Worker A
    const keepABtn = screen.getByTestId('btn-keep-a-conf-sess-01');
    fireEvent.click(keepABtn);
    expect(onResolve).toHaveBeenCalledWith('conf-sess-01', 'keep_worker_a');

    // Keep Worker B
    const keepBBtn = screen.getByTestId('btn-keep-b-conf-sess-01');
    fireEvent.click(keepBBtn);
    expect(onResolve).toHaveBeenCalledWith('conf-sess-01', 'keep_worker_b');

    // Three-way merge
    const mergeBtn = screen.getByTestId('btn-merge-conf-sess-01');
    fireEvent.click(mergeBtn);
    expect(onResolve).toHaveBeenCalledWith('conf-sess-01', 'three_way_merge');

    // Abort both
    const abortBtn = screen.getByTestId('btn-abort-conf-sess-01');
    fireEvent.click(abortBtn);
    expect(onResolve).toHaveBeenCalledWith('conf-sess-01', 'abort_both');
  });

  it('toggles expansion when clicking conflict item header', () => {
    render(<ParallelWorkConflictBanner conflicts={mockConflicts} />);

    // Initially the second item is not expanded
    expect(screen.queryByText('Worker A: worker-auth')).not.toBeInTheDocument();

    // Click toggle on second item
    const toggleBtn = screen.getByTestId('toggle-conflict-conf-sess-02');
    fireEvent.click(toggleBtn);

    expect(screen.getByText('Worker A: worker-auth')).toBeInTheDocument();
    expect(screen.getByText('Worker B: worker-perf')).toBeInTheDocument();
  });
});
