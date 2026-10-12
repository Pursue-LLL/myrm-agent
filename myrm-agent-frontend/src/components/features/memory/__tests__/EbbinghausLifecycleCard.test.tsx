/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EbbinghausLifecycleCard } from '../command-center/EbbinghausLifecycleCard';

const {
  mockEvaluateMemoryLifecycle,
  mockExportColdArchive,
  mockReviveColdMemory,
} = vi.hoisted(() => ({
  mockEvaluateMemoryLifecycle: vi.fn(),
  mockExportColdArchive: vi.fn(),
  mockReviveColdMemory: vi.fn(),
}));

vi.mock('@/services/memory/decayLifecycle', () => ({
  evaluateMemoryLifecycle: mockEvaluateMemoryLifecycle,
  exportColdArchive: mockExportColdArchive,
  reviveColdMemory: mockReviveColdMemory,
}));

describe('EbbinghausLifecycleCard', () => {
  const mockInitialReport = {
    total_evaluated: 15,
    hot_count: 5,
    warm_count: 7,
    cold_count: 3,
    migrated_count: 2,
    migrated_memory_ids: ['mem_cold_001', 'mem_cold_002'],
  };

  const mockArchiveData = {
    total_archived: 2,
    records: [
      {
        memory_id: 'mem_cold_001',
        content: 'Legacy Python 2 compatibility guideline',
        importance: 0.8,
        created_at: 1722470400,
        last_accessed_at: 1722513600,
        access_count: 3,
        pinned: false,
        score: 0.08,
        tier: 'COLD',
      },
      {
        memory_id: 'mem_cold_002',
        content: 'Deprecated API v1 endpoints reference',
        importance: 0.6,
        created_at: 1722800000,
        last_accessed_at: 1723723200,
        access_count: 1,
        pinned: false,
        score: 0.14,
        tier: 'COLD',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockEvaluateMemoryLifecycle.mockResolvedValue(mockInitialReport);
    mockExportColdArchive.mockResolvedValue(mockArchiveData);
  });

  it('renders Ebbinghaus decay metrics and tier distribution HUD', async () => {
    render(<EbbinghausLifecycleCard />);

    await waitFor(() => {
      expect(mockEvaluateMemoryLifecycle).toHaveBeenCalledTimes(1);
      expect(mockExportColdArchive).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByText(/艾宾浩斯遗忘衰减与分层生命周期/i),
    ).toBeInTheDocument();
    expect(screen.getByText('HOT 热活跃内存')).toBeInTheDocument();
    expect(screen.getByText('WARM 温向量检索')).toBeInTheDocument();
    expect(screen.getByText('COLD 冷存储归档')).toBeInTheDocument();
    expect(screen.getByText(/共评估 15 条/)).toBeInTheDocument();
    expect(
      screen.getByText(/Legacy Python 2 compatibility guideline/),
    ).toBeInTheDocument();
  });

  it('executes lifecycle evaluation and reflects migrated count update', async () => {
    render(<EbbinghausLifecycleCard />);

    await waitFor(() => {
      expect(mockEvaluateMemoryLifecycle).toHaveBeenCalledTimes(1);
    });

    mockEvaluateMemoryLifecycle.mockResolvedValueOnce({
      ...mockInitialReport,
      total_evaluated: 20,
      hot_count: 6,
      warm_count: 8,
      cold_count: 6,
      migrated_count: 4,
    });

    const evalButton = screen.getByRole('button', { name: /运行衰减评估与存储迁移/i });
    fireEvent.click(evalButton);

    await waitFor(() => {
      expect(mockEvaluateMemoryLifecycle).toHaveBeenCalledTimes(2);
      expect(
        screen.getByText(/评估流转完成：评估 20 条记忆，迁移 4 条/),
      ).toBeInTheDocument();
    });
  });

  it('submits cold memory revival and displays success indicator', async () => {
    mockReviveColdMemory.mockResolvedValueOnce({
      memory_id: 'mem_cold_001',
      old_tier: 'COLD',
      new_tier: 'HOT',
      old_score: 0.08,
      new_score: 0.95,
      access_count: 4,
    });

    render(<EbbinghausLifecycleCard />);

    await waitFor(() => {
      expect(mockEvaluateMemoryLifecycle).toHaveBeenCalledTimes(1);
    });

    const inputId = screen.getByPlaceholderText(/待唤醒记忆 ID/i);
    fireEvent.change(inputId, { target: { value: 'mem_cold_001' } });

    const reviveButton = screen.getByRole('button', { name: /激活唤醒至 HOT 层/i });
    fireEvent.click(reviveButton);

    await waitFor(() => {
      expect(mockReviveColdMemory).toHaveBeenCalledWith({
        memory_id: 'mem_cold_001',
        boost_importance: 0.9,
      });
      expect(
        screen.getByText(/冷记忆 \[mem_cold_001\] 已激活唤醒并提升至 HOT 层/),
      ).toBeInTheDocument();
    });
  });

  it('refreshes cold archive records on button click', async () => {
    render(<EbbinghausLifecycleCard />);

    await waitFor(() => {
      expect(mockExportColdArchive).toHaveBeenCalledTimes(1);
    });

    mockExportColdArchive.mockResolvedValueOnce({
      total_archived: 3,
      records: [
        ...mockArchiveData.records,
        {
          memory_id: 'mem_cold_003',
          content: 'Obsolete database migration v3',
          importance: 0.5,
          created_at: 1721462400,
          last_accessed_at: 1721462400,
          access_count: 1,
          pinned: false,
          score: 0.05,
          tier: 'COLD',
        },
      ],
    });

    const syncButton = screen.getByRole('button', { name: /同步冷归档/i });
    fireEvent.click(syncButton);

    await waitFor(() => {
      expect(mockExportColdArchive).toHaveBeenCalledTimes(2);
      expect(
        screen.getByText(/已同步 3 条冷存储归档数据切片/),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Obsolete database migration v3/),
      ).toBeInTheDocument();
    });
  });
});
