import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DeliverableSnapshotDiffModal } from '../DeliverableSnapshotDiffModal';
import type {
  DeliverableSnapshot,
  SnapshotDiffItem,
} from '../deliverableInspectorTypes';

describe('DeliverableSnapshotDiffModal', () => {
  const mockSnapshots: DeliverableSnapshot[] = [
    {
      version: 1,
      timestamp: 1757000000000,
      deliverableType: 'slides',
      nodes: [
        { id: 's-1', index: 1, title: 'Slide 1', summary: 'S1', nodeType: 'slide', content: 'C1 Old' },
        { id: 's-2', index: 2, title: 'Slide 2', summary: 'S2', nodeType: 'slide', content: 'C2' },
      ],
      changeDescription: '初始全量生成',
    },
    {
      version: 2,
      timestamp: 1757000100000,
      deliverableType: 'slides',
      nodes: [
        { id: 's-1', index: 1, title: 'Slide 1', summary: 'S1', nodeType: 'slide', content: 'C1 New' },
        { id: 's-2', index: 2, title: 'Slide 2', summary: 'S2', nodeType: 'slide', content: 'C2' },
      ],
      changeDescription: '定向微调 #1',
    },
  ];

  const mockDiffItems: SnapshotDiffItem[] = [
    {
      nodeId: 's-1',
      nodeTitle: 'Slide 1',
      status: 'modified',
      beforeContent: 'C1 Old',
      afterContent: 'C1 New',
    },
    {
      nodeId: 's-2',
      nodeTitle: 'Slide 2',
      status: 'unchanged',
    },
  ];

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <DeliverableSnapshotDiffModal
        isOpen={false}
        snapshots={mockSnapshots}
        currentVersion={2}
        diffItems={mockDiffItems}
        onRollback={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders snapshot versions and diff cards', () => {
    render(
      <DeliverableSnapshotDiffModal
        isOpen={true}
        snapshots={mockSnapshots}
        currentVersion={2}
        diffItems={mockDiffItems}
        onRollback={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('版本快照对比与安全回退')).toBeDefined();
    expect(screen.getByText('v1')).toBeDefined();
    expect(screen.getByText('v2')).toBeDefined();
    expect(screen.getByText('局部修改')).toBeDefined();
    expect(screen.getByText('原样保留')).toBeDefined();
    expect(screen.getByText('C1 Old')).toBeDefined();
    expect(screen.getByText('C1 New')).toBeDefined();
  });

  it('handles rollback to previous version and triggers callbacks', () => {
    const onRollback = vi.fn();
    const onClose = vi.fn();

    render(
      <DeliverableSnapshotDiffModal
        isOpen={true}
        snapshots={mockSnapshots}
        currentVersion={2}
        diffItems={mockDiffItems}
        onRollback={onRollback}
        onClose={onClose}
      />,
    );

    // Select version 1 chip
    const v1Btn = screen.getByRole('button', { name: /v1/i });
    fireEvent.click(v1Btn);

    // Rollback button should appear
    const rollbackBtn = screen.getByRole('button', { name: /无损回退到 v1/i });
    expect(rollbackBtn).toBeDefined();

    fireEvent.click(rollbackBtn);
    expect(onRollback).toHaveBeenCalledWith(1);
    expect(onClose).toHaveBeenCalled();
  });

  it('closes modal on close button click and escape key', () => {
    const onClose = vi.fn();

    render(
      <DeliverableSnapshotDiffModal
        isOpen={true}
        snapshots={mockSnapshots}
        currentVersion={2}
        diffItems={mockDiffItems}
        onRollback={vi.fn()}
        onClose={onClose}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: '关闭快照对比' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
