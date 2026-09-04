/** @vitest-environment jsdom */
'use client';

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import KnowledgePickerPopover from '../KnowledgePickerPopover';
import useChatStore from '@/store/useChatStore';
import * as sharedContextsApi from '@/services/memory/sharedContexts';

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
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => (
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
  useTranslations: (ns: string) => {
    return (key: string, values?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        tooltip: '挂载知识库',
        popoverTitle: '挂载知识库至当前对话',
        searchPlaceholder: '搜索可用知识库...',
        activeCount: `已挂载 ${values?.count ?? 0} 个`,
        noKnowledgeBases: '暂无可用的知识库',
        noSearchResults: '未找到匹配的知识库',
        manageKnowledge: '管理知识库',
        manage: '管理',
        maxLimitReached: '单个会话最多可同时挂载 6 个知识库',
        bindSuccess: '已成功挂载知识库',
        unbindSuccess: '已取消挂载知识库',
        actionError: '知识库挂载操作失败',
        ariaLabel: '选择要挂载的知识库',
      };
      return map[key] ?? key;
    };
  },
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
    useChatStore.setState({
      chatId: 'test-chat-123',
      activeKnowledgeBaseIds: [],
      activeKnowledgeBaseNames: {},
      incognitoMode: false,
    });
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
      created_at: 1700000000,
      updated_at: 1700000000,
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
      created_at: 1700000000,
    });

    render(<KnowledgePickerPopover />);
    const trigger = screen.getByRole('button', { name: /选择要挂载的知识库/i });
    fireEvent.click(trigger);

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
      expect(useChatStore.getState().activeKnowledgeBaseIds).toContain('kb-test-1');
    });
  });
});
