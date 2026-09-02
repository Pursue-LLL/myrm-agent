'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ToolsPanel from '../ToolsPanel';
import useToolsSnapshotStore from '@/store/useToolsSnapshotStore';
import type { ToolSnapshotItem } from '@/store/chat/types';

vi.mock('next-intl', () => ({
  useLocale: () => 'zh-CN',
  useTranslations: (ns: string) => {
    return (key: string) => {
      const map: Record<string, string> = {
        'layers.core': '核心层',
        'layers.high_priority': '高优层',
        'layers.extended': '扩展层',
        'layers.external': '外部层',
        'knownTools.conversationSearch.name': '对话搜索',
        'knownTools.conversationSearch.summary': '搜索历史对话',
        parameters: '参数',
        title: '可用工具',
        searchPlaceholder: '搜索工具...',
        noToolsFound: '未找到工具',
      };
      return map[key] ?? key;
    };
  },
}));

describe('ToolsPanel Component', () => {
  beforeEach(() => {
    useToolsSnapshotStore.setState({ tools: [] });
  });

  it('renders correctly with semantic layer badges', () => {
    const mockTools: ToolSnapshotItem[] = [
      {
        name: 'web_search_tool',
        source: 'builtin',
        layer: 'high_priority',
        summary: 'Web search tool',
      },
      {
        name: 'bash_code_execute_tool',
        source: 'builtin',
        layer: 'core',
        summary: 'Bash execution tool',
      },
      {
        name: 'pdf_reader_tool',
        source: 'builtin',
        layer: 'extended',
        summary: 'PDF reader tool',
      },
    ];

    useToolsSnapshotStore.setState({ tools: mockTools });

    render(<ToolsPanel />);

    // Open popover by clicking trigger button
    const trigger = screen.getByRole('button');
    fireEvent.click(trigger);

    expect(screen.getByText('web_search_tool')).toBeInTheDocument();
    expect(screen.getByText('bash_code_execute_tool')).toBeInTheDocument();
    expect(screen.getByText('pdf_reader_tool')).toBeInTheDocument();

    expect(screen.getByText('高优层')).toBeInTheDocument();
    expect(screen.getByText('核心层')).toBeInTheDocument();
    expect(screen.getByText('扩展层')).toBeInTheDocument();
  });
});
