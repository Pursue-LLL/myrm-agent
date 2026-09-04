/** @vitest-environment jsdom */
'use client';

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import KnowledgePickerPopover from '../KnowledgePickerPopover';
import * as sharedContextsApi from '@/services/memory/sharedContexts';

vi.mock('next/link', () => ({
  default: ({ children, href, onClick, className }: any) => (
    <a href={href} onClick={onClick} className={className}>
      {children}
    </a>
  ),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="mock-popover">{children}</div>
  ),
  PopoverTrigger: ({ children }: { children: React.ReactElement }) => (
    <div data-testid="mock-popover-trigger">{children}</div>
  ),
  PopoverContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="mock-popover-content">{children}</div>
  ),
}));

vi.mock('@/components/primitives/switch', () => ({
  Switch: ({
    checked,
    disabled,
    onCheckedChange,
    'aria-label': ariaLabel,
  }: {
    checked?: boolean;
    disabled?: boolean;
    onCheckedChange?: (checked: boolean) => void;
    'aria-label'?: string;
  }) => (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
    />
  ),
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'zh-CN',
  useTranslations: () => {
    return (key: string, values?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        tooltip: '挂载知识库',
        title: '挂载知识库',
        searchPlaceholder: '搜索可用知识库...',
        activeCount: `已挂载 ${values?.count ?? 0} 个`,
        emptyKnowledgeBases: '暂无可用的知识库',
        noSearchResults: '未找到匹配的知识库',
        manage: '管理',
        maxLimitReached: '单个会话最多可同时挂载 6 个知识库',
        operationFailed: '知识库挂载操作失败',
        ariaLabel: '选择要挂载的知识库',
      };
      return map[key] ?? key;
    };
  },
}));

const mockSetActiveKnowledgeBaseIds = vi.fn();
const mockSetActiveKnowledgeBaseNames = vi.fn();
const mockRemoveActiveKnowledgeBase = vi.fn();

let mockChatStoreState = {
  chatId: 'test-chat-123',
  activeKnowledgeBaseIds: [] as string[],
  activeKnowledgeBaseNames: {} as Record<string, string>,
  setActiveKnowledgeBaseIds: mockSetActiveKnowledgeBaseIds,
  setActiveKnowledgeBaseNames: mockSetActiveKnowledgeBaseNames,
  removeActiveKnowledgeBase: mockRemoveActiveKnowledgeBase,
  incognitoMode: false,
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: typeof mockChatStoreState) => unknown) =>
    selector(mockChatStoreState),
  ),
}));

vi.mock('@/services/memory/sharedContexts', () => ({
  listSharedContexts: vi.fn(),
  listSharedContextBindingsForTarget: vi.fn(),
  createSharedContextBinding: vi.fn(),
  deleteSharedContextBinding: vi.fn(),
}));

describe('KnowledgePickerPopover Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChatStoreState = {
      chatId: 'test-chat-123',
      activeKnowledgeBaseIds: [],
      activeKnowledgeBaseNames: {},
      setActiveKnowledgeBaseIds: mockSetActiveKnowledgeBaseIds,
      setActiveKnowledgeBaseNames: mockSetActiveKnowledgeBaseNames,
      removeActiveKnowledgeBase: mockRemoveActiveKnowledgeBase,
      incognitoMode: false,
    };
  });

  it('renders trigger button with correct accessibility and tooltip', () => {
    (sharedContextsApi.listSharedContexts as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });
    (sharedContextsApi.listSharedContextBindingsForTarget as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });

    render(<KnowledgePickerPopover />);
    const trigger = screen.getByRole('button', { name: /选择要挂载的知识库/i });
    expect(trigger).toBeDefined();
  });

  it('loads available contexts and mounts selected context on click', async () => {
    const mockContext = {
      id: 'kb-test-1',
      name: '研发规范与架构守则',
      description: '团队内部架构指南',
      status: 'active' as const,
      created_at: '2026-09-04T00:00:00Z',
      updated_at: '2026-09-04T00:00:00Z',
    };

    (sharedContextsApi.listSharedContexts as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [mockContext],
      total: 1,
    });
    (sharedContextsApi.listSharedContextBindingsForTarget as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [],
      total: 0,
    });
    (sharedContextsApi.createSharedContextBinding as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'binding-1',
      context_id: 'kb-test-1',
      target_type: 'conversation',
      target_id: 'test-chat-123',
      created_at: '2026-09-04T00:00:00Z',
    });

    render(<KnowledgePickerPopover />);

    await waitFor(() => {
      expect(screen.getByText('研发规范与架构守则')).toBeDefined();
    });

    const itemSwitch = screen.getByRole('switch', { name: /研发规范与架构守则/i });
    fireEvent.click(itemSwitch);

    await waitFor(() => {
      expect(sharedContextsApi.createSharedContextBinding).toHaveBeenCalledWith('kb-test-1', {
        target_type: 'conversation',
        target_id: 'test-chat-123',
      });
      expect(mockSetActiveKnowledgeBaseIds).toHaveBeenCalledWith(['kb-test-1']);
    });
  });
});
