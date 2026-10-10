import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as dongleService from '@/services/memory/projectDongle';
import { useProjectContextDongle } from '../useProjectContextDongle';

vi.mock('@/services/memory/projectDongle', () => ({
  initProjectDongle: vi.fn(),
  getDongleState: vi.fn(),
  getDonglePromptContext: vi.fn(),
  syncDongleBlocks: vi.fn(),
}));

describe('useProjectContextDongle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useProjectContextDongle());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isSyncing).toBe(false);
    expect(result.current.dongleState).toBeNull();
    expect(result.current.promptContext).toBeNull();
    expect(result.current.lastSyncResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('initializes workspace and refreshes state on success', async () => {
    const mockInitResp: dongleService.DongleInitResponseDTO = {
      workspace_dir: '/test/workspace',
      initialized_files: ['PROJECT_STATE.md', 'DECISIONS.md', 'LESSONS.md', 'INDEX.md'],
      message: 'Initialized 4 memory files in workspace.',
    };
    const mockState: dongleService.DongleStateDTO = {
      workspace_dir: '/test/workspace',
      project_state_blocks: [],
      decision_blocks: [],
      lesson_blocks: [],
      index_content: '# DONGLE INDEX',
      archive_pointers: [],
      total_active_blocks: 0,
    };

    vi.mocked(dongleService.initProjectDongle).mockResolvedValueOnce(mockInitResp);
    vi.mocked(dongleService.getDongleState).mockResolvedValueOnce(mockState);

    const { result } = renderHook(() => useProjectContextDongle());

    let res: dongleService.DongleInitResponseDTO | null = null;
    await act(async () => {
      res = await result.current.initWorkspace('/test/workspace');
    });

    expect(res).toEqual(mockInitResp);
    expect(result.current.dongleState).toEqual(mockState);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('loads dongle state successfully', async () => {
    const mockState: dongleService.DongleStateDTO = {
      workspace_dir: '/test/workspace',
      project_state_blocks: [
        {
          block_id: 'blk-01',
          block_type: 'PROJECT_STATE.md',
          content: 'Active milestone in progress',
          created_date: '2026-09-27',
          tags: ['m1'],
        },
      ],
      decision_blocks: [],
      lesson_blocks: [],
      index_content: '# DONGLE INDEX',
      archive_pointers: [],
      total_active_blocks: 1,
    };

    vi.mocked(dongleService.getDongleState).mockResolvedValueOnce(mockState);

    const { result } = renderHook(() => useProjectContextDongle());

    let loadedState: dongleService.DongleStateDTO | null = null;
    await act(async () => {
      loadedState = await result.current.loadState('/test/workspace');
    });

    expect(loadedState).toEqual(mockState);
    expect(result.current.dongleState).toEqual(mockState);
    expect(result.current.isLoading).toBe(false);
  });

  it('loads prompt context successfully', async () => {
    const mockPrompt = '### [PROJECT CONTEXT DONGLE - ZERO-LOSS RELAY LAYER 1]\nActive milestone in progress';
    vi.mocked(dongleService.getDonglePromptContext).mockResolvedValueOnce({
      workspace_dir: '/test/workspace',
      prompt_context: mockPrompt,
    });

    const { result } = renderHook(() => useProjectContextDongle());

    let prompt: string | null = null;
    await act(async () => {
      prompt = await result.current.loadPromptContext('/test/workspace');
    });

    expect(prompt).toBe(mockPrompt);
    expect(result.current.promptContext).toBe(mockPrompt);
  });

  it('syncs blocks and refreshes state on success', async () => {
    const mockSyncRes: dongleService.DongleSyncResponseDTO = {
      updated_files: ['DECISIONS.md', 'INDEX.md'],
      added_blocks_count: 1,
      spilled_blocks_count: 0,
      created_pointers: [],
      message: 'Synced 1 blocks into dongle files.',
    };
    const mockState: dongleService.DongleStateDTO = {
      workspace_dir: '/test/workspace',
      project_state_blocks: [],
      decision_blocks: [
        {
          block_id: 'dec-1',
          block_type: 'DECISIONS.md',
          content: 'Adopt Markdown bullet blocks',
          created_date: '2026-09-27',
        },
      ],
      lesson_blocks: [],
      index_content: '# DONGLE INDEX',
      archive_pointers: [],
      total_active_blocks: 1,
    };

    vi.mocked(dongleService.syncDongleBlocks).mockResolvedValueOnce(mockSyncRes);
    vi.mocked(dongleService.getDongleState).mockResolvedValueOnce(mockState);

    const { result } = renderHook(() => useProjectContextDongle());

    await act(async () => {
      await result.current.syncBlocks('/test/workspace', [
        {
          block_id: 'dec-1',
          block_type: 'DECISIONS.md',
          content: 'Adopt Markdown bullet blocks',
          created_date: '2026-09-27',
        },
      ]);
    });

    expect(result.current.lastSyncResult).toEqual(mockSyncRes);
    expect(result.current.dongleState).toEqual(mockState);
    expect(result.current.isSyncing).toBe(false);
  });

  it('handles error gracefully when loadState fails', async () => {
    vi.mocked(dongleService.getDongleState).mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useProjectContextDongle());

    await act(async () => {
      await result.current.loadState('/test/workspace');
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.dongleState).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });
});
