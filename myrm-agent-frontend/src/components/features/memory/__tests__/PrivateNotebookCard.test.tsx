/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/privateNotebook::listNotes, searchNotes, getNote, appendNote, rewriteNote, deleteNote,
 *   listContexts, searchHistory, switchToNewContext
 * ../command-center/PrivateNotebookCard::PrivateNotebookCard
 *
 * [OUTPUT]
 * Test suite verifying transparent inspectable model private notebook UI, notes operations, history search,
 * and context handover rotation.
 *
 * [POS]
 * Unit test for Item 89 (Transparent Inspectable Model Private Notebook Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PrivateNotebookCard } from '../command-center/PrivateNotebookCard';
import type {
  NoteMetadataDTO,
  NoteEntryDTO,
  NoteSearchResultDTO,
  HistoryContextItemDTO,
  HistoryEntryItemDTO,
  NewContextResponseDTO,
} from '@/services/memory/privateNotebook';

const {
  mockListNotes,
  mockSearchNotes,
  mockGetNote,
  mockAppendNote,
  mockRewriteNote,
  mockDeleteNote,
  mockListContexts,
  mockSearchHistory,
  mockSwitchToNewContext,
} = vi.hoisted(() => ({
  mockListNotes: vi.fn(),
  mockSearchNotes: vi.fn(),
  mockGetNote: vi.fn(),
  mockAppendNote: vi.fn(),
  mockRewriteNote: vi.fn(),
  mockDeleteNote: vi.fn(),
  mockListContexts: vi.fn(),
  mockSearchHistory: vi.fn(),
  mockSwitchToNewContext: vi.fn(),
}));

vi.mock('@/services/memory/privateNotebook', () => ({
  listNotes: mockListNotes,
  searchNotes: mockSearchNotes,
  getNote: mockGetNote,
  appendNote: mockAppendNote,
  rewriteNote: mockRewriteNote,
  deleteNote: mockDeleteNote,
  listContexts: mockListContexts,
  searchHistory: mockSearchHistory,
  switchToNewContext: mockSwitchToNewContext,
}));

describe('PrivateNotebookCard', () => {
  const sampleNotes: NoteMetadataDTO[] = [
    {
      title: 'architecture_decisions',
      char_count: 120,
      line_count: 8,
      updated_at: '2026-10-08T02:00:00Z',
      tags: ['arch', 'p0'],
    },
    {
      title: 'user_preferences',
      char_count: 65,
      line_count: 4,
      updated_at: '2026-10-08T02:10:00Z',
      tags: ['ux'],
    },
  ];

  const sampleNoteEntry: NoteEntryDTO = {
    title: 'architecture_decisions',
    content: '## 架构决议\n- 采用透明本地 Markdown 笔记\n- 跨窗口上下文无损接力',
    updated_at: '2026-10-08T02:00:00Z',
    tags: ['arch', 'p0'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockListNotes.mockResolvedValue([]);
    mockGetNote.mockResolvedValue(sampleNoteEntry);
    mockSearchNotes.mockResolvedValue([]);
    mockListContexts.mockResolvedValue([]);
    mockSearchHistory.mockResolvedValue([]);
    mockSwitchToNewContext.mockResolvedValue({
      new_context_id: 'ctx-active-default',
      previous_context_id: 'ctx-prev-default',
      carried_notes_count: 0,
      status: 'ready',
      message: 'success',
    });
  });

  it('renders correctly, loads notes, and displays HUD statistics', async () => {
    mockListNotes.mockResolvedValueOnce(sampleNotes);
    mockGetNote.mockResolvedValueOnce(sampleNoteEntry);

    render(<PrivateNotebookCard />);

    expect(screen.getByTestId('private-notebook-card')).toBeInTheDocument();
    expect(screen.getByText(/透明可检视模型私有笔记本/)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockListNotes).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId('hud-notes-count')).toHaveTextContent('2 篇');
      expect(screen.getByTestId('note-item-architecture_decisions')).toBeInTheDocument();
    });
  });

  it('populates architecture preset into input fields', async () => {
    mockListNotes.mockResolvedValueOnce([]);
    render(<PrivateNotebookCard />);

    const presetBtn = screen.getByTestId('preset-notebook-btn');
    fireEvent.click(presetBtn);

    const titleInput = screen.getByPlaceholderText(/例如: project_constraints/) as HTMLInputElement;
    expect(titleInput.value).toBe('system_architecture_spec');
  });

  it('appends a new note and refreshes list', async () => {
    mockListNotes.mockResolvedValueOnce([]);
    const createdNote: NoteEntryDTO = {
      title: 'feature_roadmap',
      content: 'Item 89 P0 闭环推进中',
      updated_at: '2026-10-08T03:00:00Z',
      tags: [],
    };
    mockAppendNote.mockResolvedValueOnce(createdNote);
    mockListNotes.mockResolvedValueOnce([
      {
        title: 'feature_roadmap',
        char_count: 20,
        line_count: 1,
        updated_at: '2026-10-08T03:00:00Z',
        tags: [],
      },
    ]);

    render(<PrivateNotebookCard />);

    const titleInput = screen.getByPlaceholderText(/例如: project_constraints/);
    const contentInput = screen.getByPlaceholderText(/输入要记录到模型的要点/);

    fireEvent.change(titleInput, { target: { value: 'feature_roadmap' } });
    fireEvent.change(contentInput, { target: { value: 'Item 89 P0 闭环推进中' } });

    const submitBtn = screen.getByTestId('append-note-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockAppendNote).toHaveBeenCalledWith({
        title: 'feature_roadmap',
        content: 'Item 89 P0 闭环推进中',
      });
      expect(screen.getByText(/已保存笔记: feature_roadmap/)).toBeInTheDocument();
    });
  });

  it('searches notes by keyword query', async () => {
    mockListNotes.mockResolvedValueOnce(sampleNotes);
    mockGetNote.mockResolvedValueOnce(sampleNoteEntry);
    const searchResults: NoteSearchResultDTO[] = [
      {
        title: 'architecture_decisions',
        score: 0.98,
        snippet: '采用透明本地 Markdown 笔记',
      },
    ];
    mockSearchNotes.mockResolvedValue(searchResults);

    render(<PrivateNotebookCard />);

    await waitFor(() => {
      expect(screen.getByTestId('hud-notes-count')).toHaveTextContent('2 篇');
    });

    const searchInput = screen.getByPlaceholderText(/检索私有笔记正文或标题关键词/);
    fireEvent.change(searchInput, { target: { value: 'Markdown' } });

    const searchForm = screen.getByTestId('search-notes-form');
    fireEvent.submit(searchForm);

    await waitFor(() => {
      expect(mockSearchNotes).toHaveBeenCalledWith('Markdown');
      expect(screen.getByTestId('search-results-box')).toHaveTextContent('匹配切片 (1)');
      expect(screen.getByTestId('search-results-box')).toHaveTextContent('采用透明本地 Markdown 笔记');
    });
  });

  it('supports human rectification edit and atomic rewrite', async () => {
    mockListNotes.mockResolvedValueOnce([sampleNotes[0]]);
    mockGetNote.mockResolvedValueOnce(sampleNoteEntry);
    const updatedNote: NoteEntryDTO = {
      ...sampleNoteEntry,
      content: '## 架构决议 (已纠偏)\n- 修复历史遗留技术债',
    };
    mockRewriteNote.mockResolvedValueOnce(updatedNote);
    mockListNotes.mockResolvedValueOnce([sampleNotes[0]]);

    render(<PrivateNotebookCard />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-note-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('edit-note-btn'));

    const textarea = screen.getByTestId('rectification-textarea');
    expect(textarea).toBeInTheDocument();
    fireEvent.change(textarea, {
      target: { value: '## 架构决议 (已纠偏)\n- 修复历史遗留技术债' },
    });

    const saveBtn = screen.getByTestId('save-note-btn');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockRewriteNote).toHaveBeenCalledWith('architecture_decisions', {
        title: 'architecture_decisions',
        content: '## 架构决议 (已纠偏)\n- 修复历史遗留技术债',
      });
      expect(screen.getByText(/已人工纠偏覆写笔记: architecture_decisions/)).toBeInTheDocument();
    });
  });

  it('deletes a private note', async () => {
    mockListNotes.mockResolvedValueOnce([sampleNotes[0]]);
    mockGetNote.mockResolvedValueOnce(sampleNoteEntry);
    mockDeleteNote.mockResolvedValueOnce({
      status: 'success',
      deleted: true,
      title: 'architecture_decisions',
    });
    mockListNotes.mockResolvedValueOnce([]);

    render(<PrivateNotebookCard />);

    await waitFor(() => {
      expect(screen.getByTestId('delete-note-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('delete-note-btn'));

    await waitFor(() => {
      expect(mockDeleteNote).toHaveBeenCalledWith('architecture_decisions');
      expect(screen.getByText(/已删除笔记: architecture_decisions/)).toBeInTheDocument();
    });
  });

  it('searches interaction history in History Tab', async () => {
    mockListNotes.mockResolvedValueOnce([]);
    const historyEntries: HistoryEntryItemDTO[] = [
      {
        context_id: 'ctx-archived-001',
        turn_index: 3,
        role: 'assistant',
        content: '已将关键结论保存至私有笔记',
        created_at: '2026-10-08T01:30:00Z',
      },
    ];
    const contexts: HistoryContextItemDTO[] = [
      {
        context_id: 'ctx-archived-001',
        title: '初始任务会话',
        turn_count: 5,
        created_at: '2026-10-08T01:00:00Z',
      },
    ];
    mockListContexts.mockResolvedValueOnce(contexts);
    mockSearchHistory.mockResolvedValueOnce(historyEntries);

    render(<PrivateNotebookCard />);

    const historyTab = screen.getByTestId('tab-history');
    fireEvent.click(historyTab);

    await waitFor(() => {
      expect(mockListContexts).toHaveBeenCalled();
      expect(screen.getByText('ctx-archived-001')).toBeInTheDocument();
    });

    const searchHistoryInput = screen.getByPlaceholderText(/搜索历史所有上下文窗口/);
    fireEvent.change(searchHistoryInput, { target: { value: '私有笔记' } });

    const searchHistoryBtn = screen.getByTestId('search-history-btn');
    fireEvent.click(searchHistoryBtn);

    await waitFor(() => {
      expect(mockSearchHistory).toHaveBeenCalledWith('私有笔记');
      expect(screen.getByText(/已将关键结论保存至私有笔记/)).toBeInTheDocument();
    });
  });

  it('executes smooth context handover rotation in Handover Tab', async () => {
    mockListNotes.mockResolvedValueOnce(sampleNotes);
    const handoverOutcome: NewContextResponseDTO = {
      new_context_id: 'ctx-active-002',
      previous_context_id: 'ctx-main-001',
      carried_notes_count: 2,
      status: 'ready',
      message: 'Clean context window created with 2 notes carried over',
    };
    mockSwitchToNewContext.mockResolvedValue(handoverOutcome);

    render(<PrivateNotebookCard />);

    await waitFor(() => {
      expect(screen.getByTestId('hud-notes-count')).toBeInTheDocument();
    });

    const handoverTab = screen.getByTestId('tab-handover');
    fireEvent.click(handoverTab);

    const reasonTextarea = screen.getByTestId('handover-reason-textarea');
    fireEvent.change(reasonTextarea, {
      target: { value: '阶段任务达成，清理执行冗余，平滑接力' },
    });

    const handoverForm = screen.getByTestId('handover-form');
    fireEvent.submit(handoverForm);

    await waitFor(() => {
      expect(mockSwitchToNewContext).toHaveBeenCalledWith({
        summary_reason: '阶段任务达成，清理执行冗余，平滑接力',
      });
      expect(screen.getByTestId('handover-result-box')).toBeInTheDocument();
      expect(screen.getByTestId('handover-result-box')).toHaveTextContent('ctx-active-002');
      expect(screen.getByTestId('hud-active-context')).toHaveTextContent('ctx-active-002');
      expect(screen.getByText(/接力移交成功/)).toBeInTheDocument();
    });
  });
});
