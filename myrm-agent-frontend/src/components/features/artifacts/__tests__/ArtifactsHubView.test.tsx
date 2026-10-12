import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ArtifactsHubView from '../ArtifactsHubView';
import * as artifactService from '@/services/artifactProvenance';

// Mock next-intl
vi.mock('next-intl', () => {
  // Stable reference: a fresh translator per render re-triggers effects keyed on `t`.
  const t = (key: string, values?: Record<string, string | number>) => {
    const translations: Record<string, string> = {
      title: '全景产物溯源大盘',
      subtitle: '集中检索与管理各会话产生的文档、代码、数据表格与交付物',
      searchPlaceholder: '按产物名称、描述或扩展名搜索...',
      tabAll: '全部产物',
      tabDocument: '文档资料',
      tabCode: '代码脚本',
      tabData: '数据表格',
      tabMedia: '多媒体图表',
      tabLink: '提取链接',
      tabOther: '其他',
      navToSession: '直达来源会话',
      originSession: '来源会话',
      associatedAgent: '所属智能体',
      download: '下载产物',
      exportZip: '一键打包导出 ZIP',
      emptyTitle: '暂无产物资产',
      emptyDesc: '在与智能体对话中生成的交付物与文件将自动沉淀在此处',
    };
    return translations[key] || key;
  };
  return { useTranslations: () => t };
});

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

const mockItems: artifactService.ArtifactProvenanceItem[] = [
  {
    id: 'art-1',
    name: 'architecture_doc.md',
    description: 'Core system design document',
    category: 'document',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T12:00:00Z',
    chat_id: 'chat-alpha',
    chat_title: 'System Design Discussion',
    agent_id: 'architect-agent',
    latest_version_id: 'v-1',
    vault_uri: 'vault://doc-1',
    sha256_hash: 'hash1',
    commit_message: 'Initial draft',
    size_bytes: 4096,
    extension: 'md',
  },
  {
    id: 'art-2',
    name: 'data_pipeline.py',
    description: 'ETL runner script',
    category: 'code',
    created_at: '2026-09-02T10:00:00Z',
    updated_at: '2026-09-02T11:00:00Z',
    chat_id: 'chat-beta',
    chat_title: 'Data Ops Automation',
    agent_id: 'data-agent',
    latest_version_id: 'v-2',
    vault_uri: 'vault://code-1',
    sha256_hash: 'hash2',
    commit_message: 'Add error handling',
    size_bytes: 2048,
    extension: 'py',
  },
];

const mockStats: artifactService.ArtifactCategoryStats = {
  all: 2,
  document: 1,
  code: 1,
  data: 0,
  media: 0,
  link: 0,
  other: 0,
};

describe('ArtifactsHubView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(artifactService, 'fetchArtifactProvenance').mockResolvedValue({
      items: mockItems,
      total: 2,
      stats: mockStats,
    });
  });

  it('renders header, category tabs with stats, and artifact cards', async () => {
    render(<ArtifactsHubView />);

    expect(screen.getByText('全景产物溯源大盘')).toBeDefined();
    expect(screen.getByText('集中检索与管理各会话产生的文档、代码、数据表格与交付物')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('architecture_doc.md')).toBeDefined();
      expect(screen.getByText('data_pipeline.py')).toBeDefined();
      expect(screen.getByText('System Design Discussion')).toBeDefined();
      expect(screen.getByText('Data Ops Automation')).toBeDefined();
    });
  });

  it('switches category tabs and triggers service filter', async () => {
    render(<ArtifactsHubView />);

    await waitFor(() => {
      expect(screen.getByText('architecture_doc.md')).toBeDefined();
    });

    const codeTab = screen.getByRole('button', { name: /代码脚本/ });
    fireEvent.click(codeTab);

    await waitFor(() => {
      expect(artifactService.fetchArtifactProvenance).toHaveBeenCalledWith(
        expect.objectContaining({
          category: 'code',
        }),
      );
    });
  });

  it('navigates to source session when clicking navToSession button', async () => {
    render(<ArtifactsHubView />);

    await waitFor(() => {
      expect(screen.getByText('architecture_doc.md')).toBeDefined();
    });

    const navButtons = screen.getAllByRole('button', { name: /直达来源会话/ });
    fireEvent.click(navButtons[0]);

    expect(mockPush).toHaveBeenCalledWith('/chat/chat-alpha');
  });

  it('enables batch export button when selecting artifact checkboxes', async () => {
    render(<ArtifactsHubView />);

    await waitFor(() => {
      expect(screen.getByText('architecture_doc.md')).toBeDefined();
    });

    // Checkboxes are rendered on each card
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBe(2);

    fireEvent.click(checkboxes[0]);

    // Batch export button should appear
    expect(screen.getByRole('button', { name: /一键打包导出 ZIP/ })).toBeDefined();
  });
});
