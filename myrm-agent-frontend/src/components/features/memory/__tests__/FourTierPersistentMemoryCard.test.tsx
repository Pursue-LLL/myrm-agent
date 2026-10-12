/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/fourTierFts::listFourTierMemories, saveFourTierMemory,
 *   deleteFourTierMemory, searchFourTierFts, runFourTierDreamCompaction
 * ../command-center/FourTierPersistentMemoryCard::FourTierPersistentMemoryCard
 *
 * [OUTPUT]
 * Test suite verifying four-tier persistent memory (project, session, progress, global),
 * millisecond SQLite FTS5 BM25 search, and /dream maintenance compaction cycle.
 *
 * [POS]
 * Unit test for Item 92 (Four-Tier Persistent Memory and FTS5 Self-Maintenance Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FourTierPersistentMemoryCard } from '../command-center/FourTierPersistentMemoryCard';
import type {
  FourTierMemoryItemDTO,
  FtsSearchResultDTO,
  DreamCompactionReportDTO,
} from '@/services/memory/fourTierFts';

const {
  mockListFourTierMemories,
  mockSaveFourTierMemory,
  mockDeleteFourTierMemory,
  mockSearchFourTierFts,
  mockRunFourTierDreamCompaction,
} = vi.hoisted(() => ({
  mockListFourTierMemories: vi.fn(),
  mockSaveFourTierMemory: vi.fn(),
  mockDeleteFourTierMemory: vi.fn(),
  mockSearchFourTierFts: vi.fn(),
  mockRunFourTierDreamCompaction: vi.fn(),
}));

vi.mock('@/services/memory/fourTierFts', () => ({
  listFourTierMemories: mockListFourTierMemories,
  saveFourTierMemory: mockSaveFourTierMemory,
  deleteFourTierMemory: mockDeleteFourTierMemory,
  searchFourTierFts: mockSearchFourTierFts,
  runFourTierDreamCompaction: mockRunFourTierDreamCompaction,
}));

describe('FourTierPersistentMemoryCard', () => {
  const sampleItems: FourTierMemoryItemDTO[] = [
    {
      item_id: 'mem_test_proj',
      scope: 'project',
      title: 'Project Architecture',
      content: 'Project code uses hexagonal decoupled structure.',
      project_hash: 'proj_test',
      session_id: '',
      tags: ['architecture'],
      created_at: '2026-10-08T01:00:00Z',
      updated_at: '2026-10-08T01:00:00Z',
    },
    {
      item_id: 'mem_test_sess',
      scope: 'session',
      title: 'Session Checkpoint #1',
      content: 'State saved at turn 10 for checkpoint restore.',
      project_hash: 'proj_test',
      session_id: 'sess_1',
      tags: ['checkpoint'],
      created_at: '2026-10-08T02:00:00Z',
      updated_at: '2026-10-08T02:00:00Z',
    },
    {
      item_id: 'mem_test_prog',
      scope: 'progress',
      title: 'Step 2 Parsing Done',
      content: 'Progress completed 80% on AST migration.',
      project_hash: 'proj_test',
      session_id: 'sess_1',
      tags: ['progress'],
      created_at: '2026-10-08T02:30:00Z',
      updated_at: '2026-10-08T02:30:00Z',
    },
    {
      item_id: 'mem_test_glob',
      scope: 'global',
      title: 'Global Style Habit',
      content: 'Developer likes concise code with strict type safety.',
      project_hash: 'default',
      session_id: '',
      tags: ['style'],
      created_at: '2026-10-08T00:30:00Z',
      updated_at: '2026-10-08T00:30:00Z',
    },
  ];

  const sampleSearchResults: FtsSearchResultDTO[] = [
    {
      item_id: 'mem_test_proj',
      scope: 'project',
      project_hash: 'proj_test',
      title: 'Project Architecture',
      content: 'Project code uses hexagonal decoupled structure.',
      snippet: 'uses hexagonal decoupled structure',
      bm25_rank: -1.52,
      updated_at: '2026-10-08T01:00:00Z',
    },
  ];

  const sampleDreamReport: DreamCompactionReportDTO = {
    dream_id: 'dream_test_cycle_01',
    scanned_items_count: 8,
    merged_items_count: 2,
    pruned_items_count: 1,
    retained_items_count: 5,
    duration_ms: 165.2,
    created_at: '2026-10-08T03:00:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockListFourTierMemories.mockResolvedValue(sampleItems);
    mockSearchFourTierFts.mockResolvedValue(sampleSearchResults);
    mockRunFourTierDreamCompaction.mockResolvedValue(sampleDreamReport);
  });

  it('renders HUD metrics and project tier items on mount', async () => {
    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(mockListFourTierMemories).toHaveBeenCalled();
    });

    expect(screen.getByTestId('hud-project-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-session-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-progress-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-global-count')).toHaveTextContent('1');
    expect(screen.getAllByText('Project Architecture')[0]).toBeInTheDocument();
  });

  it('switches between 4 memory scopes (project, session, progress, global)', async () => {
    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByTestId('scope-tab-project')).toBeInTheDocument();
    });

    // Switch to session scope
    fireEvent.click(screen.getByTestId('scope-tab-session'));
    expect(screen.getAllByText('Session Checkpoint #1')[0]).toBeInTheDocument();

    // Switch to progress scope
    fireEvent.click(screen.getByTestId('scope-tab-progress'));
    expect(screen.getAllByText('Step 2 Parsing Done')[0]).toBeInTheDocument();

    // Switch to global scope
    fireEvent.click(screen.getByTestId('scope-tab-global'));
    expect(screen.getAllByText('Global Style Habit')[0]).toBeInTheDocument();
  });

  it('inspects selected memory item and deletes it', async () => {
    mockDeleteFourTierMemory.mockResolvedValueOnce({ deleted: true, item_id: 'mem_test_proj' });

    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tier-item-card-mem_test_proj')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tier-item-card-mem_test_proj'));

    const detailBox = screen.getByTestId('tier-item-detail-box');
    expect(detailBox).toHaveTextContent('Project Architecture');
    expect(detailBox).toHaveTextContent('Project code uses hexagonal decoupled structure.');

    const deleteBtn = screen.getByTestId('delete-tier-item-button');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mockDeleteFourTierMemory).toHaveBeenCalledWith('mem_test_proj');
    });
  });

  it('creates a new four-tier persistent memory via form', async () => {
    const createdItem: FourTierMemoryItemDTO = {
      item_id: 'mem_new_created',
      scope: 'project',
      title: 'Database Pooling Rule',
      content: 'Set max pool size to 30 for high concurrency.',
      project_hash: 'default',
      session_id: '',
      tags: ['db', 'pool'],
      created_at: '2026-10-08T03:10:00Z',
      updated_at: '2026-10-08T03:10:00Z',
    };
    mockSaveFourTierMemory.mockResolvedValueOnce(createdItem);

    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByText('录入新记忆')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('录入新记忆'));

    const titleInput = screen.getByLabelText('记忆标题 / 标识 (Title)');
    const contentInput = screen.getByLabelText('记忆详情内容 (Content)');
    const tagsInput = screen.getByLabelText('标签（英文逗号分隔）');

    fireEvent.change(titleInput, { target: { value: 'Database Pooling Rule' } });
    fireEvent.change(contentInput, { target: { value: 'Set max pool size to 30 for high concurrency.' } });
    fireEvent.change(tagsInput, { target: { value: 'db, pool' } });

    const form = screen.getByTestId('add-four-tier-memory-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSaveFourTierMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          scope: 'project',
          title: 'Database Pooling Rule',
          content: 'Set max pool size to 30 for high concurrency.',
        })
      );
    });

    expect((await screen.findAllByText('Database Pooling Rule'))[0]).toBeInTheDocument();
  });

  it('switches to search and dream tab and executes FTS5 BM25 search', async () => {
    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-search-and-dream')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-search-and-dream'));
    expect(screen.getByTestId('four-tier-fts-search-and-dream-view')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText(/输入关键词/);
    fireEvent.change(searchInput, { target: { value: 'hexagonal' } });

    const searchButton = screen.getByTestId('fts-search-button');
    fireEvent.click(searchButton);

    await waitFor(() => {
      expect(mockSearchFourTierFts).toHaveBeenCalledWith('hexagonal', undefined);
    });

    expect(screen.getByTestId('fts-results-box')).toHaveTextContent('Project Architecture');
    expect(screen.getByTestId('fts-results-box')).toHaveTextContent('BM25: -1.52');
  });

  it('triggers /dream background self-maintenance compaction', async () => {
    render(<FourTierPersistentMemoryCard />);

    fireEvent.click(screen.getByTestId('tab-search-and-dream'));

    await waitFor(() => {
      expect(screen.getByTestId('trigger-dream-compaction-button')).toBeInTheDocument();
    });

    const purgeInput = screen.getByLabelText('进度记忆清理阈值（天）:');
    fireEvent.change(purgeInput, { target: { value: '14' } });

    const dreamButton = screen.getByTestId('trigger-dream-compaction-button');
    fireEvent.click(dreamButton);

    await waitFor(() => {
      expect(mockRunFourTierDreamCompaction).toHaveBeenCalledWith(
        expect.objectContaining({
          purge_progress_days: 14,
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('dream-report-box')).toBeInTheDocument();
    });

    const reportBox = screen.getByTestId('dream-report-box');
    expect(reportBox).toHaveTextContent('dream_test_cycle_01');
    expect(reportBox).toHaveTextContent('165.2ms');
    expect(reportBox).toHaveTextContent('8');
    expect(reportBox).toHaveTextContent('2');
  });

  it('triggers refresh button to re-fetch memories', async () => {
    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByText('刷新')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('刷新'));

    await waitFor(() => {
      expect(mockListFourTierMemories).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully falls back when API calls throw network error', async () => {
    mockListFourTierMemories.mockRejectedValueOnce(new Error('Network error'));

    render(<FourTierPersistentMemoryCard />);

    await waitFor(() => {
      expect(screen.getByTestId('four-tier-persistent-memory-card')).toBeInTheDocument();
    });

    // Fallback fixtures rendered without unhandled crash
    expect(screen.getAllByText('Repo Architecture & Decoupling')[0]).toBeInTheDocument();
  });
});
