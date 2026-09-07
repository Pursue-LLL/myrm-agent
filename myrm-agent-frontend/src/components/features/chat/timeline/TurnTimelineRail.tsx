'use client';

/**
 * [INPUT]
 * @/store/useChatStore::useChatStore (POS: 会话轮次投影列表与 loadThrough 控制器)
 *
 * [OUTPUT]
 * TurnTimelineRail: 10px 固定步长高密度轮次导航导轨 (对标 DeepSeek Harness web-turn-rail-outline-jump)
 *
 * [POS]
 * 会话时间线导轨组件。百轮长会话下零 DOM 抖动、支持已加载状态感知、悬浮气泡摘要预览与键盘快捷切换。
 */

import React, { useEffect, useMemo, useState, useCallback } from 'react';
import useChatStore from '@/store/useChatStore';
import { useTranslations } from 'next-intl';

export const TurnTimelineRail: React.FC = () => {
  const t = useTranslations('chat');
  const turnOutlines = useChatStore((s) => s.turnOutlines);
  const messages = useChatStore((s) => s.messages);
  const activeTurnIndex = useChatStore((s) => s.activeTimelineTurnIndex);
  const setActiveTurnIndex = useChatStore((s) => s.setActiveTimelineTurnIndex);
  const loadThrough = useChatStore((s) => s.loadThrough);

  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // 计算已载入内存的用户消息 ID 集合
  const loadedMessageIds = useMemo(() => {
    return new Set(messages.map((m) => m.id || m.messageId));
  }, [messages]);

  // 滚动并高亮目标轮次
  const scrollToTurn = useCallback(
    async (turnIndex: number, userMessageId: string) => {
      setActiveTurnIndex(turnIndex);
      // 若尚未载入内存，触发连续向前分页 loadThrough
      if (!loadedMessageIds.has(userMessageId)) {
        await loadThrough(userMessageId);
      }

      // 定位 DOM 元素
      const selector = `[data-message-id="${userMessageId}"], #msg-${userMessageId}, #message-${userMessageId}`;
      const el = document.querySelector(selector);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },
    [loadedMessageIds, loadThrough, setActiveTurnIndex],
  );

  // 快捷键支持：Alt + Up / Alt + Down 快速跳跃轮次
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!e.altKey || turnOutlines.length === 0) return;
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const currentIdx = activeTurnIndex ?? turnOutlines[turnOutlines.length - 1].turn_index;
        const target = Math.max(1, currentIdx - 1);
        const item = turnOutlines.find((t) => t.turn_index === target);
        if (item) {
          void scrollToTurn(target, item.user_message_id);
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        const currentIdx = activeTurnIndex ?? 1;
        const target = Math.min(turnOutlines.length, currentIdx + 1);
        const item = turnOutlines.find((t) => t.turn_index === target);
        if (item) {
          void scrollToTurn(target, item.user_message_id);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [turnOutlines, activeTurnIndex, scrollToTurn]);

  // 如果会话轮次小于 2，不占据额外右侧导轨空间
  if (!turnOutlines || turnOutlines.length < 2) {
    return null;
  }

  return (
    <div
      data-testid="turn-timeline-rail"
      className="fixed right-3 top-1/2 -translate-y-1/2 z-30 hidden md:flex flex-col items-center gap-1.5 py-3 px-1 rounded-full bg-background/60 hover:bg-background/90 backdrop-blur-md border border-border/40 shadow-sm transition-all duration-200"
    >
      {turnOutlines.map((turn) => {
        const isLoaded = loadedMessageIds.has(turn.user_message_id);
        const isActive = activeTurnIndex === turn.turn_index;
        const isHovered = hoveredIndex === turn.turn_index;

        return (
          <div
            key={turn.turn_index}
            className="relative flex items-center group cursor-pointer"
            onMouseEnter={() => setHoveredIndex(turn.turn_index)}
            onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => void scrollToTurn(turn.turn_index, turn.user_message_id)}
          >
            {/* 导轨单点：固定 10px 高度/步长，已加载亮调，未加载暗调 */}
            <div
              className={`w-2 h-2.5 rounded-full transition-all duration-200 ${
                isActive
                  ? 'w-2.5 h-4 bg-primary shadow-sm scale-110'
                  : isLoaded
                    ? 'bg-foreground/50 hover:bg-primary/80 hover:h-3.5'
                    : 'bg-muted-foreground/30 hover:bg-muted-foreground/60'
              }`}
            />

            {/* 悬浮气泡预览 (Hover Tooltip Outline) */}
            {isHovered && (
              <div
                data-testid={`turn-preview-${turn.turn_index}`}
                className="absolute right-6 top-1/2 -translate-y-1/2 w-64 p-2.5 rounded-lg bg-popover/95 text-popover-foreground border border-border shadow-md backdrop-blur-md text-xs pointer-events-none animate-in fade-in zoom-in-95 duration-150 z-50"
              >
                <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-border/50 font-medium">
                  <span className="text-primary font-mono font-semibold">
                    Turn #{turn.turn_index}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {isLoaded ? t('timeline.loaded', { defaultMessage: '已载入' }) : t('timeline.lazyLoad', { defaultMessage: '未载入 (点击加载)' })}
                  </span>
                </div>
                <div className="text-foreground/90 font-medium line-clamp-2 mb-1">
                  {turn.prompt_preview || t('timeline.noPrompt', { defaultMessage: '无提示词' })}
                </div>
                {turn.reply_preview && (
                  <div className="text-muted-foreground text-[11px] line-clamp-2 border-l-2 border-primary/40 pl-1.5">
                    {turn.reply_preview}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
