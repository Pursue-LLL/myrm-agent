/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/revocableProvenance::listProvenanceMemories, forgetMemory,
 *   saveProvenanceMemory, listDreamDiaries, recordDreamDiary
 * ../command-center/RevocableProvenanceCard::RevocableProvenanceCard
 *
 * [OUTPUT]
 * Test suite verifying bidirectional provenance memory graph inspection,
 * atomic memory forget (tombstone registration with raw transcript preservation),
 * and transparent background dream diary consolidation.
 *
 * [POS]
 * Unit test for Item 91 (Revocable Provenance-Qualified Memory and Dream Diary Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RevocableProvenanceCard } from '../command-center/RevocableProvenanceCard';
import type {
  ProvenanceQualifiedMemoryDTO,
  ForgetResultDTO,
  DreamDiaryEntryDTO,
} from '@/services/memory/revocableProvenance';

const {
  mockListProvenanceMemories,
  mockForgetMemory,
  mockSaveProvenanceMemory,
  mockListDreamDiaries,
  mockRecordDreamDiary,
} = vi.hoisted(() => ({
  mockListProvenanceMemories: vi.fn(),
  mockForgetMemory: vi.fn(),
  mockSaveProvenanceMemory: vi.fn(),
  mockListDreamDiaries: vi.fn(),
  mockRecordDreamDiary: vi.fn(),
}));

vi.mock('@/services/memory/revocableProvenance', () => ({
  listProvenanceMemories: mockListProvenanceMemories,
  forgetMemory: mockForgetMemory,
  saveProvenanceMemory: mockSaveProvenanceMemory,
  listDreamDiaries: mockListDreamDiaries,
  recordDreamDiary: mockRecordDreamDiary,
}));

describe('RevocableProvenanceCard', () => {
  const sampleMemories: ProvenanceQualifiedMemoryDTO[] = [
    {
      memory_id: 'mem_test_001',
      statement: '必须使用领域驱动设计与纯粹业务层。',
      category: 'architecture_pattern',
      provenance: {
        session_id: 'session_arch_alpha',
        message_id: 'msg_round_10',
        turn_index: 10,
        quote_snippet: '所有业务逻辑都应该与底层框架解耦。',
        extracted_at: '2026-10-08T02:00:00Z',
        confidence_score: 0.96,
      },
      is_revoked: false,
      revoked_at: null,
      revocation_reason: '',
      created_at: '2026-10-08T02:00:00Z',
      updated_at: '2026-10-08T02:00:00Z',
    },
    {
      memory_id: 'mem_test_002',
      statement: '旧版持久化采用单一大宽表存储。',
      category: 'database_legacy',
      provenance: {
        session_id: 'session_db_beta',
        message_id: 'msg_round_02',
        turn_index: 2,
        quote_snippet: '为了快速验证先使用大宽表。',
        extracted_at: '2026-10-08T02:05:00Z',
        confidence_score: 0.91,
      },
      is_revoked: true,
      revoked_at: '2026-10-08T02:10:00Z',
      revocation_reason: '已重构为规范化关系模式',
      created_at: '2026-10-08T02:05:00Z',
      updated_at: '2026-10-08T02:10:00Z',
    },
  ];

  const sampleDiaries: DreamDiaryEntryDTO[] = [
    {
      dream_id: 'dream_test_01',
      agent_id: 'agent_primary_01',
      scanned_turns: 15,
      promoted_memory_ids: ['mem_test_001'],
      pruned_duplicates_count: 5,
      duration_ms: 220.5,
      status: 'completed',
      notes: '梦境整理完成：沉淀领域驱动架构，剔除冗余临时调试信息。',
      created_at: '2026-10-08T02:20:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockListProvenanceMemories.mockResolvedValue(sampleMemories);
    mockListDreamDiaries.mockResolvedValue(sampleDiaries);
  });

  it('renders HUD metrics and active provenance memories on mount', async () => {
    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(mockListProvenanceMemories).toHaveBeenCalledWith(true);
      expect(mockListDreamDiaries).toHaveBeenCalled();
    });

    expect(screen.getByTestId('hud-active-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-revoked-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-diaries-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-pruned-count')).toHaveTextContent('5');
    expect(screen.getByText('必须使用领域驱动设计与纯粹业务层。')).toBeInTheDocument();
  });

  it('allows tab switching between memories and dream diaries', async () => {
    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-memories')).toBeInTheDocument();
    });

    // Switch to dream diaries tab
    fireEvent.click(screen.getByTestId('tab-dream-diaries'));
    expect(screen.getByTestId('dream-diary-deck-view')).toBeInTheDocument();
    expect(screen.getByText('dream_test_01')).toBeInTheDocument();
    expect(screen.getByText('agent_primary_01')).toBeInTheDocument();

    // Switch back to memories tab
    fireEvent.click(screen.getByTestId('tab-memories'));
    expect(screen.getByTestId('provenance-qualified-memory-list-view')).toBeInTheDocument();
  });

  it('inspects bidirectional provenance metadata upon memory selection', async () => {
    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(screen.getByTestId('memory-card-mem_test_001')).toBeInTheDocument();
    });

    // Click on active memory
    fireEvent.click(screen.getByTestId('memory-card-mem_test_001'));

    await waitFor(() => {
      expect(screen.getByTestId('provenance-detail-box')).toBeInTheDocument();
    });

    const detailBox = screen.getByTestId('provenance-detail-box');
    expect(detailBox).toHaveTextContent('session_arch_alpha');
    expect(detailBox).toHaveTextContent('msg_round_10');
    expect(detailBox).toHaveTextContent('Turn #10');
    expect(detailBox).toHaveTextContent('所有业务逻辑都应该与底层框架解耦。');
    expect(detailBox).toHaveTextContent('96.0%');
  });

  it('executes atomic memory forget and updates memory state to revoked', async () => {
    const forgetResult: ForgetResultDTO = {
      memory_id: 'mem_test_001',
      revoked: true,
      source_session_id: 'session_arch_alpha',
      source_message_id: 'msg_round_10',
      message: 'Memory revoked atomically',
      transcript_intact: true,
    };
    mockForgetMemory.mockResolvedValueOnce(forgetResult);

    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(screen.getByTestId('memory-card-mem_test_001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('memory-card-mem_test_001'));

    const reasonInput = screen.getByLabelText('撤销理由 / 纠正说明（可选）');
    fireEvent.change(reasonInput, { target: { value: '业务规范已升级' } });

    const forgetButton = screen.getByTestId('forget-memory-button');
    fireEvent.click(forgetButton);

    await waitFor(() => {
      expect(mockForgetMemory).toHaveBeenCalledWith('mem_test_001', '业务规范已升级');
    });

    // Revocation status confirmed
    await waitFor(() => {
      expect(screen.getByText('已执行原子定点遗忘 (Memory Forget)')).toBeInTheDocument();
    });
  });

  it('creates a new provenance-qualified memory via form', async () => {
    const newSavedMemory: ProvenanceQualifiedMemoryDTO = {
      memory_id: 'mem_new_999',
      statement: '禁止直接操作全局状态，需通过统一调度器。',
      category: 'state_management',
      provenance: {
        session_id: 'session_dev_arch',
        message_id: 'msg_arch_42',
        turn_index: 1,
        quote_snippet: '状态管理必须单一数据流。',
        extracted_at: '2026-10-08T03:00:00Z',
        confidence_score: 0.95,
      },
      is_revoked: false,
      revoked_at: null,
      revocation_reason: '',
      created_at: '2026-10-08T03:00:00Z',
      updated_at: '2026-10-08T03:00:00Z',
    };
    mockSaveProvenanceMemory.mockResolvedValueOnce(newSavedMemory);

    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(screen.getByText('录入溯源事实')).toBeInTheDocument();
    });

    // Expand form
    fireEvent.click(screen.getByText('录入溯源事实'));

    const stmtInput = screen.getByLabelText('提炼事实 (Statement)');
    const quoteInput = screen.getByLabelText('原文佐证引文 (Verbatim Quote Snippet)');

    fireEvent.change(stmtInput, { target: { value: '禁止直接操作全局状态，需通过统一调度器。' } });
    fireEvent.change(quoteInput, { target: { value: '状态管理必须单一数据流。' } });

    const form = screen.getByTestId('add-provenance-memory-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSaveProvenanceMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          statement: '禁止直接操作全局状态，需通过统一调度器。',
          quote_snippet: '状态管理必须单一数据流。',
        })
      );
    });

    expect(await screen.findByText('禁止直接操作全局状态，需通过统一调度器。')).toBeInTheDocument();
  });

  it('records a new dream diary entry via trigger form', async () => {
    const newDiaryEntry: DreamDiaryEntryDTO = {
      dream_id: 'dream_manual_02',
      agent_id: 'agent-custom-99',
      scanned_turns: 20,
      promoted_memory_ids: ['mem_dream_001'],
      pruned_duplicates_count: 6,
      duration_ms: 310.0,
      status: 'completed',
      notes: '手动触发夜间梦境提炼成功。',
      created_at: '2026-10-08T03:10:00Z',
    };
    mockRecordDreamDiary.mockResolvedValueOnce(newDiaryEntry);

    render(<RevocableProvenanceCard />);

    // Switch to dream diaries tab
    fireEvent.click(screen.getByTestId('tab-dream-diaries'));

    await waitFor(() => {
      expect(screen.getByText('记录梦境提炼')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('记录梦境提炼'));

    const agentInput = screen.getByLabelText('目标 Agent ID');
    fireEvent.change(agentInput, { target: { value: 'agent-custom-99' } });

    const notesInput = screen.getByLabelText('蒸馏提炼总结 / 梦境心得');
    fireEvent.change(notesInput, { target: { value: '手动触发夜间梦境提炼成功。' } });

    const form = screen.getByTestId('record-dream-diary-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockRecordDreamDiary).toHaveBeenCalledWith(
        expect.objectContaining({
          agent_id: 'agent-custom-99',
          notes: '手动触发夜间梦境提炼成功。',
        })
      );
    });

    expect(await screen.findByText('dream_manual_02')).toBeInTheDocument();
  });

  it('triggers refresh button to re-fetch memories and diaries', async () => {
    render(<RevocableProvenanceCard />);

    await waitFor(() => {
      expect(screen.getByText('刷新')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('刷新'));

    await waitFor(() => {
      expect(mockListProvenanceMemories).toHaveBeenCalledTimes(2);
      expect(mockListDreamDiaries).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully falls back when API calls throw network error', async () => {
    mockListProvenanceMemories.mockRejectedValueOnce(new Error('Network error'));
    mockListDreamDiaries.mockRejectedValueOnce(new Error('Network error'));

    render(<RevocableProvenanceCard />);

    // Renders fallback data without throwing
    await waitFor(() => {
      expect(screen.getByTestId('revocable-provenance-card')).toBeInTheDocument();
    });

    expect(screen.getByText(/核心业务层必须使用六边形架构/)).toBeInTheDocument();
  });
});
