/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/curatorStudio::fetchCuratorEntries, fetchCuratorSummary, exportCuratorMarkdown,
 *   createCuratorEntry, updateCuratorEntry, auditCuratorEntry, eraseCuratorEntry, syncFromMarkdown
 * ../command-center/MemoryCuratorStudioCard::MemoryCuratorStudioCard
 *
 * [OUTPUT]
 * Test suite verifying transparent Markdown mirror bi-directional sync,
 * anti-misremembering human confirmation gate, and WYSIWYG card stream curation.
 *
 * [POS]
 * Unit test for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemoryCuratorStudioCard } from '../command-center/MemoryCuratorStudioCard';
import type {
  CuratedMemoryEntryDTO,
  CuratorStudioSummaryDTO,
  MarkdownSyncResponseDTO,
} from '@/services/memory/curatorStudio';

const {
  mockFetchCuratorEntries,
  mockFetchCuratorSummary,
  mockExportCuratorMarkdown,
  mockCreateCuratorEntry,
  mockUpdateCuratorEntry,
  mockAuditCuratorEntry,
  mockEraseCuratorEntry,
  mockSyncFromMarkdown,
} = vi.hoisted(() => ({
  mockFetchCuratorEntries: vi.fn(),
  mockFetchCuratorSummary: vi.fn(),
  mockExportCuratorMarkdown: vi.fn(),
  mockCreateCuratorEntry: vi.fn(),
  mockUpdateCuratorEntry: vi.fn(),
  mockAuditCuratorEntry: vi.fn(),
  mockEraseCuratorEntry: vi.fn(),
  mockSyncFromMarkdown: vi.fn(),
}));

vi.mock('@/services/memory/curatorStudio', () => ({
  fetchCuratorEntries: mockFetchCuratorEntries,
  fetchCuratorSummary: mockFetchCuratorSummary,
  exportCuratorMarkdown: mockExportCuratorMarkdown,
  createCuratorEntry: mockCreateCuratorEntry,
  updateCuratorEntry: mockUpdateCuratorEntry,
  auditCuratorEntry: mockAuditCuratorEntry,
  eraseCuratorEntry: mockEraseCuratorEntry,
  syncFromMarkdown: mockSyncFromMarkdown,
}));

describe('MemoryCuratorStudioCard', () => {
  const sampleEntries: CuratedMemoryEntryDTO[] = [
    {
      entry_id: 'mem_pref_01',
      category: 'preference',
      title: '界面深色主题偏好',
      content: '用户明确偏好暗色界面与高对比度字体渲染。',
      confidence: 1.0,
      status: 'confirmed',
      tags: ['ui', 'theme'],
      created_at: '2026-10-08T04:00:00Z',
      updated_at: '2026-10-08T04:00:00Z',
    },
    {
      entry_id: 'mem_fact_02',
      category: 'fact',
      title: '前端架构技术栈',
      content: '项目采用 React 19 + TailwindCSS v4 + Vite + Bun。',
      confidence: 0.95,
      status: 'confirmed',
      tags: ['tech', 'stack'],
      created_at: '2026-10-08T04:10:00Z',
      updated_at: '2026-10-08T04:10:00Z',
    },
    {
      entry_id: 'mem_gate_04',
      category: 'preference',
      title: '夜间免打扰模式推断',
      content: 'AI 自发推断：用户可能偏好在 22:00 后静音非紧急系统通知。',
      confidence: 0.72,
      status: 'pending_confirmation',
      tags: ['notification'],
      created_at: '2026-10-08T04:20:00Z',
      updated_at: '2026-10-08T04:20:00Z',
    },
  ];

  const sampleSummary: CuratorStudioSummaryDTO = {
    total_entries: 3,
    confirmed_count: 2,
    pending_count: 1,
    rejected_count: 0,
    archived_count: 0,
    categories_breakdown: { preference: 2, fact: 1 },
  };

  const sampleMarkdown = `# Workspace Memory Mirror\n\n## Preferences\n- [x] **界面深色主题偏好** (id: mem_pref_01, confidence: 1.00): 用户明确偏好暗色界面与高对比度字体渲染。\n- [ ] **夜间免打扰模式推断** (id: mem_gate_04, confidence: 0.72): AI 自发推断：用户可能偏好在 22:00 后静音非紧急系统通知。\n\n## Facts\n- [x] **前端架构技术栈** (id: mem_fact_02, confidence: 0.95): 项目采用 React 19 + TailwindCSS v4 + Vite + Bun。\n`;

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchCuratorEntries.mockResolvedValue(sampleEntries);
    mockFetchCuratorSummary.mockResolvedValue(sampleSummary);
    mockExportCuratorMarkdown.mockResolvedValue(sampleMarkdown);
  });

  it('renders the card header and 4-dimension HUD metrics', async () => {
    render(<MemoryCuratorStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('记忆策展工作台与 Markdown 双向同步')).toBeInTheDocument();
      expect(screen.getByText('Item 101 · P0')).toBeInTheDocument();
      expect(screen.getByText('待审门禁 (Human Gate)')).toBeInTheDocument();
      expect(screen.getByText('双向镜像同步')).toBeInTheDocument();
    });

    expect(screen.getByText('所见即所得卡片流')).toBeInTheDocument();
    expect(screen.getByText('工作区 Markdown 镜像')).toBeInTheDocument();
  });

  it('renders card stream items with status tags and human gate badges', async () => {
    render(<MemoryCuratorStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('界面深色主题偏好')).toBeInTheDocument();
      expect(screen.getByText('前端架构技术栈')).toBeInTheDocument();
      expect(screen.getByText('夜间免打扰模式推断')).toBeInTheDocument();
      expect(screen.getByText('待人类门禁确认')).toBeInTheDocument();
    });
  });

  it('audits and confirms a pending memory candidate when clicking confirm', async () => {
    const updatedEntry: CuratedMemoryEntryDTO = {
      ...sampleEntries[2],
      status: 'confirmed',
    };
    mockAuditCuratorEntry.mockResolvedValue(updatedEntry);

    render(<MemoryCuratorStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('确认采纳')).toBeInTheDocument();
    });

    const confirmButton = screen.getByRole('button', { name: /确认记忆 夜间免打扰模式推断/ });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mockAuditCuratorEntry).toHaveBeenCalledWith('mem_gate_04', true);
    });
  });

  it('switches to Workspace Markdown tab and shows mirror editor', async () => {
    render(<MemoryCuratorStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('工作区 Markdown 镜像')).toBeInTheDocument();
    });

    const markdownTabButton = screen.getByRole('button', {
      name: '切换到工作区 Markdown 镜像对账工作台',
    });
    fireEvent.click(markdownTabButton);

    await waitFor(() => {
      expect(screen.getByText('工作区 Markdown 镜像 (MEMORY.md)')).toBeInTheDocument();
      expect(screen.getByText('热重载同步至 SQLite')).toBeInTheDocument();
      expect(screen.getByLabelText('实时 Markdown 纯文本编辑器 (支持即时手写编辑)')).toBeInTheDocument();
    });
  });

  it('triggers bi-directional sync from Markdown and renders reconciliation diff', async () => {
    const syncResult: MarkdownSyncResponseDTO = {
      added_count: 1,
      updated_count: 1,
      deleted_count: 0,
      added_entries: [],
      updated_entries: [],
      deleted_entry_ids: [],
    };
    mockSyncFromMarkdown.mockResolvedValue(syncResult);

    render(<MemoryCuratorStudioCard />);

    const markdownTabButton = screen.getByRole('button', {
      name: '切换到工作区 Markdown 镜像对账工作台',
    });
    fireEvent.click(markdownTabButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '热重载双向对账同步' })).toBeInTheDocument();
    });

    const syncButton = screen.getByRole('button', { name: '热重载双向对账同步' });
    fireEvent.click(syncButton);

    await waitFor(() => {
      expect(mockSyncFromMarkdown).toHaveBeenCalled();
      expect(screen.getByText('最近双向对账结果')).toBeInTheDocument();
      expect(screen.getByText('+1 新增')).toBeInTheDocument();
      expect(screen.getByText('~1 修改')).toBeInTheDocument();
    });
  });

  it('filters curated cards by search input', async () => {
    render(<MemoryCuratorStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('界面深色主题偏好')).toBeInTheDocument();
      expect(screen.getByText('前端架构技术栈')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('搜索记忆标题、内容或标签...');
    fireEvent.change(searchInput, { target: { value: '技术栈' } });

    await waitFor(() => {
      expect(screen.getByText('前端架构技术栈')).toBeInTheDocument();
      expect(screen.queryByText('界面深色主题偏好')).not.toBeInTheDocument();
    });
  });
});
