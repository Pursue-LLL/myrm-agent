/**
 * [INPUT]
 * LocalStorage keys: 'myrm:tool_picker:pinned', 'myrm:tool_picker:recent'
 * Window CustomEvent: 'toolpicker:toggle'
 *
 * [OUTPUT]
 * - ToolCategory: 'all' | 'system' | 'browser' | 'code' | 'docs'
 * - CategorizedToolItem: Core tool entity
 * - useCategorizedToolPicker: Hook managing category tabs, instant pinyin/fuzzy filter, and pinning
 *
 * [POS]
 * Hook layer for CategorizedToolPickerWithPinningAndInstantFilter (Item 15).
 * Single file < 250 lines. Zero `any` types.
 */

'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';

export type ToolCategory = 'all' | 'system' | 'browser' | 'code' | 'docs';
export type ToolSource = 'builtin' | 'skill' | 'mcp';

export interface CategorizedToolItem {
  id: string;
  name: string;
  displayName: string;
  description: string;
  category: Exclude<ToolCategory, 'all'>;
  source: ToolSource;
  pinyinTokens: string[];
  enabled: boolean;
}

export const PRESET_TOOLS: CategorizedToolItem[] = [
  {
    id: 'computer_control',
    name: 'computer_control',
    displayName: '电脑与系统控制',
    description: '通过鼠标、键盘和屏幕截图接管操作系统，自动化完成桌面软件操作',
    category: 'system',
    source: 'builtin',
    pinyinTokens: ['dnkz', 'diannaokongzhi', 'computer', 'system', 'os'],
    enabled: true,
  },
  {
    id: 'bash_terminal',
    name: 'bash_terminal',
    displayName: '终端命令执行',
    description: '在安全隔离的沙箱或宿主终端中执行 Shell 命令与进程控制',
    category: 'system',
    source: 'builtin',
    pinyinTokens: ['zdml', 'zhongduan', 'bash', 'terminal', 'sh'],
    enabled: true,
  },
  {
    id: 'browser_playwright',
    name: 'browser_playwright',
    displayName: '无头浏览器与网页提取',
    description: '模拟人类浏览网页、提取动态 DOM 内容、填写表单并截取全屏快照',
    category: 'browser',
    source: 'builtin',
    pinyinTokens: ['llq', 'liulanqi', 'browser', 'playwright', 'web'],
    enabled: true,
  },
  {
    id: 'web_search_tavily',
    name: 'web_search_tavily',
    displayName: '全网智能实时搜索',
    description: '聚合 Google、Bing 与垂直学术索引，检索高时效性一手权威资讯',
    category: 'browser',
    source: 'builtin',
    pinyinTokens: ['ss', 'sousuo', 'search', 'tavily', 'google'],
    enabled: true,
  },
  {
    id: 'python_data_interpreter',
    name: 'python_data_interpreter',
    displayName: 'Python 代码执行与数据分析',
    description: '在专用 Jupyter 沙箱执行 Python 代码，绘制统计图表与清洗表格',
    category: 'code',
    source: 'skill',
    pinyinTokens: ['py', 'python', 'sjfx', 'shujufenxi', 'jupyter'],
    enabled: true,
  },
  {
    id: 'git_codebase_inspector',
    name: 'git_codebase_inspector',
    displayName: 'Git 仓库与代码库全景审阅',
    description: '语义解析 AST 代码树、分析 Git Commit 历史与分支 Pull Request 差异',
    category: 'code',
    source: 'skill',
    pinyinTokens: ['git', 'dmk', 'daimaku', 'codebase', 'repo'],
    enabled: true,
  },
  {
    id: 'doc_knowledge_retriever',
    name: 'doc_knowledge_retriever',
    displayName: '多维文档与向量知识库检索',
    description: '支持 PDF/Markdown/Word 深度切片与稠密向量混合语义召回',
    category: 'docs',
    source: 'mcp',
    pinyinTokens: ['wd', 'wendang', 'zsk', 'zhishiku', 'docs', 'pdf'],
    enabled: true,
  },
  {
    id: 'sheets_multidimensional_table',
    name: 'sheets_multidimensional_table',
    displayName: '多维表格与电子表格操作',
    description: '读取、写入与批量更新 Excel 与飞书/Notion 兼容多维表格记录',
    category: 'docs',
    source: 'mcp',
    pinyinTokens: ['bg', 'biaoge', 'sheets', 'excel', 'table'],
    enabled: true,
  },
];

const PINNED_STORAGE_KEY = 'myrm:tool_picker:pinned';
const RECENT_STORAGE_KEY = 'myrm:tool_picker:recent';
const DEFAULT_PINNED = ['computer_control', 'browser_playwright'];

export function useCategorizedToolPicker() {
  const [tools, setTools] = useState<CategorizedToolItem[]>(PRESET_TOOLS);
  const [activeCategory, setActiveCategory] = useState<ToolCategory>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [pinnedIds, setPinnedIds] = useState<string[]>(DEFAULT_PINNED);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  // Initialize from LocalStorage
  useEffect(() => {
    try {
      const storedPinned = localStorage.getItem(PINNED_STORAGE_KEY);
      if (storedPinned) {
        setPinnedIds(JSON.parse(storedPinned) as string[]);
      }
      const storedRecent = localStorage.getItem(RECENT_STORAGE_KEY);
      if (storedRecent) {
        setRecentIds(JSON.parse(storedRecent) as string[]);
      }
    } catch {
      // LocalStorage access fallback
    }
  }, []);

  const togglePin = useCallback((id: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((item) => item !== id)
        : [...prev, id];
      try {
        localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Fallback
      }
      return next;
    });
  }, []);

  const recordRecent = useCallback((id: string) => {
    setRecentIds((prev) => {
      const next = [id, ...prev.filter((item) => item !== id)].slice(0, 5);
      try {
        localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Fallback
      }
      return next;
    });
  }, []);

  const toggleToolEnabled = useCallback((id: string) => {
    setTools((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, enabled: !item.enabled } : item,
      ),
    );
  }, []);

  // Filter tools based on category and instant search query
  const filteredTools = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return tools.filter((tool) => {
      // Category filter
      if (activeCategory !== 'all' && tool.category !== activeCategory) {
        return false;
      }
      // Query filter (name, displayName, description, pinyin tokens)
      if (!query) {
        return true;
      }
      const matchesName = tool.name.toLowerCase().includes(query);
      const matchesDisplay = tool.displayName.toLowerCase().includes(query);
      const matchesDesc = tool.description.toLowerCase().includes(query);
      const matchesPinyin = tool.pinyinTokens.some((tok) =>
        tok.toLowerCase().includes(query),
      );
      return matchesName || matchesDisplay || matchesDesc || matchesPinyin;
    });
  }, [tools, activeCategory, searchQuery]);

  const pinnedTools = useMemo(() => {
    return tools.filter((tool) => pinnedIds.includes(tool.id));
  }, [tools, pinnedIds]);

  const recentTools = useMemo(() => {
    return recentIds
      .map((id) => tools.find((t) => t.id === id))
      .filter((t): t is CategorizedToolItem => Boolean(t));
  }, [tools, recentIds]);

  return {
    tools,
    activeCategory,
    setActiveCategory,
    searchQuery,
    setSearchQuery,
    pinnedIds,
    togglePin,
    recentIds,
    recordRecent,
    toggleToolEnabled,
    filteredTools,
    pinnedTools,
    recentTools,
    isOpen,
    setIsOpen,
  };
}
