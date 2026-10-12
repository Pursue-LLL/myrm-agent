import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as stalenessService from '@/services/memory/stalenessConsolidation';
import { useStalenessConsolidation } from '../useStalenessConsolidation';

vi.mock('@/services/memory/stalenessConsolidation', () => ({
  registerMemory: vi.fn(),
  listMemories: vi.fn(),
  getMemory: vi.fn(),
  touchMemoryRecall: vi.fn(),
  runMemoryAudit: vi.fn(),
  applyConsolidation: vi.fn(),
  archiveMemories: vi.fn(),
}));

describe('useStalenessConsolidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockItem: stalenessService.MemoryItemProfileDTO = {
    memory_id: 'mem_style_01',
    content: 'Always use 2 spaces indentation in TS',
    category: 'style',
    created_at: '2026-10-10T10:00:00Z',
    last_recalled_at: '2026-10-10T10:00:00Z',
    recalled_count: 0,
    staleness_score: 0.05,
    status: 'active',
    referenced_paths: ['tsconfig.json'],
    referenced_assertions: [],
    invalidation_reason: null,
    subsumed_by_id: null,
  };

  const mockAuditReport: stalenessService.MemoryAuditReportDTO = {
    total_items: 3,
    active_items: 2,
    stale_items: 1,
    invalidated_items: 0,
    consolidated_items: 0,
    archived_items: 0,
    average_staleness: 0.25,
    invalidated_results: [],
    consolidation_proposals: [
      {
        proposal_id: 'prop_style_01',
        source_memory_ids: ['mem_style_01', 'mem_style_02'],
        category: 'style',
        proposed_content: 'Unified TS code style rules',
        rationale: 'Merge fragmented formatting guidelines',
      },
    ],
    generated_at: '2026-10-10T12:00:00Z',
  };

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useStalenessConsolidation());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isAuditing).toBe(false);
    expect(result.current.memories).toEqual([]);
    expect(result.current.auditReport).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches and registers memories successfully', async () => {
    vi.mocked(stalenessService.listMemories).mockResolvedValueOnce([mockItem]);

    const { result } = renderHook(() => useStalenessConsolidation());

    let fetched: stalenessService.MemoryItemProfileDTO[] = [];
    await act(async () => {
      fetched = await result.current.fetchMemories('active');
    });

    expect(fetched).toEqual([mockItem]);
    expect(result.current.memories).toEqual([mockItem]);

    // Register a new memory
    const newItem: stalenessService.MemoryItemProfileDTO = {
      ...mockItem,
      memory_id: 'mem_style_02',
      content: 'Prefer arrow functions for callbacks',
    };
    vi.mocked(stalenessService.registerMemory).mockResolvedValueOnce(newItem);

    let created: stalenessService.MemoryItemProfileDTO | null = null;
    await act(async () => {
      created = await result.current.addMemory({
        memory_id: 'mem_style_02',
        content: 'Prefer arrow functions for callbacks',
        category: 'style',
      });
    });

    expect(created).toEqual(newItem);
    expect(result.current.memories).toHaveLength(2);
  });

  it('touches memory recall to refresh hit frequency', async () => {
    const touchedItem: stalenessService.MemoryItemProfileDTO = {
      ...mockItem,
      recalled_count: 1,
      staleness_score: 0.01,
      last_recalled_at: '2026-10-10T11:00:00Z',
    };
    vi.mocked(stalenessService.touchMemoryRecall).mockResolvedValueOnce(touchedItem);

    const { result } = renderHook(() => useStalenessConsolidation());

    let touched: stalenessService.MemoryItemProfileDTO | null = null;
    await act(async () => {
      touched = await result.current.touchRecall({
        memory_id: 'mem_style_01',
        now_iso: '2026-10-10T11:00:00Z',
      });
    });

    expect(touched).toEqual(touchedItem);
    expect((touched as stalenessService.MemoryItemProfileDTO | null)?.recalled_count).toBe(1);
  });

  it('runs memory audit scan and stores audit report', async () => {
    vi.mocked(stalenessService.runMemoryAudit).mockResolvedValueOnce(mockAuditReport);

    const { result } = renderHook(() => useStalenessConsolidation());

    let report: stalenessService.MemoryAuditReportDTO | null = null;
    await act(async () => {
      report = await result.current.audit({
        workspace_dir: '/workspace',
        now_iso: '2026-10-10T12:00:00Z',
      });
    });

    expect(report).toEqual(mockAuditReport);
    expect(result.current.auditReport).toEqual(mockAuditReport);
    expect(result.current.auditReport?.consolidation_proposals).toHaveLength(1);
  });

  it('executes consolidation and archives memories', async () => {
    const consolidatedItem: stalenessService.MemoryItemProfileDTO = {
      memory_id: 'mem_cons_prop_style_01',
      content: 'Unified TS code style rules',
      category: 'style',
      created_at: '2026-10-10T12:00:00Z',
      last_recalled_at: '2026-10-10T12:00:00Z',
      recalled_count: 1,
      staleness_score: 0.0,
      status: 'active',
      referenced_paths: [],
      referenced_assertions: [],
      invalidation_reason: null,
      subsumed_by_id: null,
    };

    vi.mocked(stalenessService.applyConsolidation).mockResolvedValueOnce(consolidatedItem);
    vi.mocked(stalenessService.listMemories).mockResolvedValueOnce([consolidatedItem]);

    const { result } = renderHook(() => useStalenessConsolidation());

    let applied: stalenessService.MemoryItemProfileDTO | null = null;
    await act(async () => {
      applied = await result.current.consolidate('prop_style_01');
    });

    expect(applied).toEqual(consolidatedItem);
    expect(result.current.memories).toEqual([consolidatedItem]);

    // Archive
    vi.mocked(stalenessService.archiveMemories).mockResolvedValueOnce(['mem_cons_prop_style_01']);

    let archivedIds: string[] = [];
    await act(async () => {
      archivedIds = await result.current.archive(['mem_cons_prop_style_01']);
    });

    expect(archivedIds).toEqual(['mem_cons_prop_style_01']);
    expect(result.current.memories[0].status).toBe('archived');
  });
});
