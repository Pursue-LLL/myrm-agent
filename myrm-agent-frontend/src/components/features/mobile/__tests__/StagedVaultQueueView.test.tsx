/** @vitest-environment jsdom */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { StagingRecord } from '@/store/offline/offlineStagingStore';
import { StagedVaultQueueView } from '../StagedVaultQueueView';

describe('StagedVaultQueueView', () => {
  it('renders empty label when records is empty', () => {
    render(
      <StagedVaultQueueView
        records={[]}
        titleLabel="待同步项"
        emptyLabel="暂无暂存笔记"
        untitledLabel="未命名笔记"
      />,
    );

    expect(screen.getByText('待同步项')).toBeInTheDocument();
    expect(screen.getByText('暂无暂存笔记')).toBeInTheDocument();
  });

  it('renders records with title and status badge', () => {
    const mockRecords: StagingRecord[] = [
      {
        id: 'rec-1',
        payload: { title: 'Explicit Title', content: 'Some body text' },
        envelope: {
          version: 1,
          ciphertext: 'c1',
          iv: 'iv1',
          salt: 's1',
          algorithm: 'AES-GCM-256',
          createdAt: 1760000000000,
        },
        status: 'synced',
        createdAt: 1760000000000,
        updatedAt: 1760000000000,
        retryCount: 0,
      },
      {
        id: 'rec-2',
        payload: { content: 'Content without title fallback test' },
        envelope: {
          version: 1,
          ciphertext: 'c2',
          iv: 'iv2',
          salt: 's2',
          algorithm: 'AES-GCM-256',
          createdAt: 1760000001000,
        },
        status: 'staged',
        createdAt: 1760000001000,
        updatedAt: 1760000001000,
        retryCount: 1,
      },
    ];

    render(
      <StagedVaultQueueView
        records={mockRecords}
        titleLabel="待同步项"
        emptyLabel="暂无暂存笔记"
        untitledLabel="未命名笔记"
      />,
    );

    expect(screen.getByText('Explicit Title')).toBeInTheDocument();
    expect(screen.getByText('Some body text')).toBeInTheDocument();
    expect(screen.getByText('synced')).toBeInTheDocument();

    expect(screen.getByText('Content without title fa')).toBeInTheDocument();
    expect(screen.getByText('staged')).toBeInTheDocument();
  });

  it('triggers onConvertToTask callback when convert button is clicked', () => {
    const handleConvertToTask = vi.fn();
    const mockRecords: StagingRecord[] = [
      {
        id: 'rec-test-convert',
        payload: { content: '整理会议纪要并生成待办' },
        envelope: {
          version: 1,
          ciphertext: 'c3',
          iv: 'iv3',
          salt: 's3',
          algorithm: 'AES-GCM-256',
          createdAt: 1760000002000,
        },
        status: 'staged',
        createdAt: 1760000002000,
        updatedAt: 1760000002000,
        retryCount: 0,
      },
    ];

    render(
      <StagedVaultQueueView
        records={mockRecords}
        titleLabel="待同步项"
        emptyLabel="暂无暂存笔记"
        untitledLabel="未命名笔记"
        convertToTaskLabel="派发任务"
        onConvertToTask={handleConvertToTask}
      />,
    );

    const convertBtn = screen.getByTestId('staging-convert-task-rec-test-convert');
    expect(convertBtn).toBeInTheDocument();
    fireEvent.click(convertBtn);

    expect(handleConvertToTask).toHaveBeenCalledTimes(1);
    expect(handleConvertToTask).toHaveBeenCalledWith('整理会议纪要并生成待办');
  });
});
