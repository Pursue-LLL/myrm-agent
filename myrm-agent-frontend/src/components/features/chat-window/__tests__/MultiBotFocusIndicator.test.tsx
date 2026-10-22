import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  MultiBotFocusIndicator,
  BotFocusSnapshotData,
} from '../MultiBotFocusIndicator';

describe('MultiBotFocusIndicator', () => {
  const mockSnapshots: BotFocusSnapshotData[] = [
    {
      bot_id: 'bot_lead',
      is_viewport_active: true,
      last_active_turn: 3,
      focus_score: 103.0,
      updated_at: '2026-10-15T12:00:00Z',
    },
    {
      bot_id: 'bot_worker',
      is_viewport_active: false,
      last_active_turn: 2,
      focus_score: 2.0,
      updated_at: '2026-10-15T11:59:00Z',
    },
  ];

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/multi-bot/focus')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                session_id: 'chat-test-1',
                focused_bot_id: 'bot_lead',
                snapshots: mockSnapshots,
              },
            }),
          });
        }
        if (url.includes('/multi-bot/compaction/evaluate')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                should_compact: true,
                reason: 'High-watermark exceeded and anti-thrash hysteresis clear',
                current_tokens: 9200,
                max_context_tokens: 10000,
                cooldown_remaining: 0,
                evaluated_at: '2026-10-15T12:01:00Z',
              },
            }),
          });
        }
        if (url.includes('/multi-bot/streams/prune')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                pruned_card_ids: ['card_abandoned_1'],
                count: 1,
              },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ data: {} }),
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders indicator dialog with snapshots and focused bot correctly', () => {
    const handleDismiss = vi.fn();
    const handleMention = vi.fn();

    render(
      <MultiBotFocusIndicator
        chatId="chat-test-1"
        initialSnapshots={mockSnapshots}
        initialFocusedBotId="bot_lead"
        onMentionSelect={handleMention}
        onDismiss={handleDismiss}
      />,
    );

    expect(screen.getByText('多Bot焦点与防抖压实')).toBeInTheDocument();
    expect(screen.getAllByText('@bot_lead').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('视口内')).toBeInTheDocument();
    expect(screen.getByText('@bot_worker')).toBeInTheDocument();

    const mentionButtons = screen.getAllByRole('button', { name: '提及' });
    fireEvent.click(mentionButtons[0]);
    expect(handleMention).toHaveBeenCalledWith('bot_lead');

    const closeButton = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeButton);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches to compaction tab and evaluates anti-thrash rules', async () => {
    render(
      <MultiBotFocusIndicator
        chatId="chat-test-1"
        initialSnapshots={mockSnapshots}
        initialFocusedBotId="bot_lead"
      />,
    );

    const compactionTab = screen.getByRole('button', { name: '防抖压实' });
    fireEvent.click(compactionTab);

    expect(screen.getByText('防抖迟滞门禁规则')).toBeInTheDocument();
    expect(screen.getByText('高水位触发门槛: 90% Context Window')).toBeInTheDocument();

    const evaluateButton = screen.getByRole('button', { name: '运行防抖压实评估' });
    await act(async () => {
      fireEvent.click(evaluateButton);
    });

    expect(screen.getByText('建议执行上下文压实')).toBeInTheDocument();
    expect(
      screen.getByText('High-watermark exceeded and anti-thrash hysteresis clear'),
    ).toBeInTheDocument();
  });

  it('switches to streams tab and prunes abandoned task cards', async () => {
    render(
      <MultiBotFocusIndicator
        chatId="chat-test-1"
        initialSnapshots={mockSnapshots}
        initialFocusedBotId="bot_lead"
      />,
    );

    const streamsTab = screen.getByRole('button', { name: '流式卫士' });
    fireEvent.click(streamsTab);

    expect(screen.getByText(/监控多Bot并发流式任务卡片/)).toBeInTheDocument();

    const pruneButton = screen.getByRole('button', { name: '扫描并清理超时僵尸流' });
    await act(async () => {
      fireEvent.click(pruneButton);
    });

    expect(screen.getByText('已清理 1 个僵尸流卡片')).toBeInTheDocument();
  });

  it('fetches focus state on mount when snapshots are empty', async () => {
    await act(async () => {
      render(<MultiBotFocusIndicator chatId="chat-test-1" />);
    });

    expect(global.fetch).toHaveBeenCalledWith('/api/chats/chat-test-1/multi-bot/focus');
  });
});
