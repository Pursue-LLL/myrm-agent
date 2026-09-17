import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import WorkingStateBadge from '../WorkingStateBadge';
import * as memoryService from '@/services/memory';

vi.mock('@/services/memory', () => ({
  getWorkingState: vi.fn(),
}));

let mockChatState = { loading: false, chatId: 'chat-alpha' };

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (s: typeof mockChatState) => unknown) => selector(mockChatState),
}));

describe('WorkingStateBadge Container', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockChatState = { loading: false, chatId: 'chat-alpha' };
  });

  it('renders nothing when response has no content and no live_state', async () => {
    vi.mocked(memoryService.getWorkingState).mockResolvedValueOnce({
      content: null,
      updated_at: null,
      ttl_days: 7,
      expired: false,
      live_state: null,
    });

    const { container } = render(<WorkingStateBadge />);
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders WorkingMemoryBoard when live_state is returned', async () => {
    vi.mocked(memoryService.getWorkingState).mockResolvedValueOnce({
      content: null,
      updated_at: '2026-09-17T00:00:00Z',
      ttl_days: 7,
      expired: false,
      live_state: {
        goal: '清洗财务报表',
        subtasks: [
          { id: 'st-1', title: '抓取SEC文件', status: 'completed' },
          { id: 'st-2', title: '转换Excel', status: 'in_progress' },
        ],
        traps: [
          {
            fingerprint: 'err-429',
            avoidance_rule: '添加自定义 User-Agent 规避限流',
            resolved: true,
          },
        ],
        active_turn: 2,
        consolidated: false,
      },
    });

    render(<WorkingStateBadge />);

    await waitFor(() => {
      expect(screen.getByText('清洗财务报表')).toBeInTheDocument();
      expect(screen.getByText('抓取SEC文件')).toBeInTheDocument();
      expect(screen.getByText('转换Excel')).toBeInTheDocument();
      expect(screen.getByText('1/2 (50%)')).toBeInTheDocument();
      expect(screen.getByText('添加自定义 User-Agent 规避限流')).toBeInTheDocument();
    });
  });

  it('renders fallback goal when only legacy content is provided', async () => {
    vi.mocked(memoryService.getWorkingState).mockResolvedValueOnce({
      content: '历史遗留纯文本任务',
      updated_at: '2026-09-17T00:00:00Z',
      ttl_days: 7,
      expired: false,
      live_state: null,
    });

    render(<WorkingStateBadge />);

    await waitFor(() => {
      expect(screen.getByText('历史遗留纯文本任务')).toBeInTheDocument();
    });
  });

  it('resets local state when chatId session changes', async () => {
    vi.mocked(memoryService.getWorkingState).mockResolvedValueOnce({
      content: '旧会话任务',
      updated_at: '2026-09-17T00:00:00Z',
      ttl_days: 7,
      expired: false,
      live_state: null,
    });

    const { rerender } = render(<WorkingStateBadge />);
    await waitFor(() => {
      expect(screen.getByText('旧会话任务')).toBeInTheDocument();
    });

    // Switch chatId
    mockChatState = { loading: false, chatId: 'chat-beta' };
    vi.mocked(memoryService.getWorkingState).mockResolvedValueOnce({
      content: null,
      updated_at: null,
      ttl_days: 7,
      expired: false,
      live_state: null,
    });

    rerender(<WorkingStateBadge />);
    await waitFor(() => {
      expect(screen.queryByText('旧会话任务')).not.toBeInTheDocument();
    });
  });
});
