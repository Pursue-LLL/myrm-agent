/**
 * 会话时间线大纲导航导轨组件 (TurnTimelineRail)
 *
 * [INPUT]
 * - messages: Message[] (POS: 当前内存中已加载的聊天消息列表)
 * - turnOutlines?: TurnOutlineItem[] (POS: 全会话轻量轮次大纲投影)
 * - activeViewportTurn?: number | null (POS: 视口当前可见阅读轮次序号，用于阅读罗盘高亮)
 * - onJump: (messageIndex: number) => void (POS: 内存消息索引跳转回调)
 * - onJumpToMessageId?: (messageId: string) => void (POS: 消息 ID 精准定位回调)
 * - onLoadThroughTurn?: (userMessageId: string) => Promise<boolean> (POS: 目标轮次连续分页拉取驱动器，按用户消息 ID 锚定)
 * - loading?: boolean (POS: 是否正在流式生成)
 * - hasGoalPanel?: boolean (POS: 目标面板是否开启，用于右侧定位偏移)
 *
 * [OUTPUT]
 * - TurnTimelineRail: PC 端固定间距 (10px Fixed-Pitch) 垂直时间线导轨（含 Alt+↑/↓ 键盘轮次跳跃）
 * - MobileTurnOutlineSheet: 移动端全景大纲抽屉导航
 *
 * [POS]
 * 长会话全景导航核心组件。支持已加载/未加载双态刻度、In-Flight 流式轮次动态合成、
 * 视口阅读进度实时罗盘联动、键盘快捷切换与双帧调度防抖动精准锚定。
 */

'use client';

import React, { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import {
  MIN_TURNS_FOR_RAIL,
  calculateRailPitchWidth,
  normalizeRailItems,
  type RailTurnItem,
} from './turnRailModel';

interface TurnTimelineRailProps {
  messages: Message[];
  turnOutlines?: TurnOutlineItem[];
  activeViewportTurn?: number | null;
  onJump: (messageIndex: number) => void;
  onJumpToMessageId?: (messageId: string) => void;
  onLoadThroughTurn?: (userMessageId: string) => Promise<boolean>;
  loading?: boolean;
  hasGoalPanel?: boolean;
}

export const TurnTimelineRail = memo<TurnTimelineRailProps>(
  ({
    messages,
    turnOutlines,
    activeViewportTurn,
    onJump,
    onJumpToMessageId,
    onLoadThroughTurn,
    loading,
    hasGoalPanel,
  }) => {
    const t = useTranslations('chat.turnRail');
    const [hoveredIdx, setHoveredIdx] = useState(-1);
    const [showPreview, setShowPreview] = useState(false);
    const [loadingTurnIndex, setLoadingTurnIndex] = useState<number | null>(null);
    const barRef = useRef<HTMLDivElement>(null);
    const previewTopRef = useRef(0);

    const railItems = useMemo(
      () => normalizeRailItems(messages, turnOutlines),
      [messages, turnOutlines],
    );

    const handleMouseMove = useCallback(
      (e: React.MouseEvent) => {
        const el = barRef.current;
        if (!el) {
          return;
        }
        const ticks = el.querySelectorAll<HTMLElement>('[data-rail-tick]');
        const barRect = el.getBoundingClientRect();
        let closest = -1;
        let closestDist = Infinity;

        ticks.forEach((tick, i) => {
          const r = tick.getBoundingClientRect();
          const midY = r.top + r.height / 2;
          const dist = Math.abs(e.clientY - midY);
          if (dist < closestDist) {
            closestDist = dist;
            closest = i;
            previewTopRef.current = midY - barRect.top;
          }
        });

        if (closest >= 0 && closest < railItems.length) {
          setHoveredIdx(closest);
          setShowPreview(true);
        }
      },
      [railItems.length],
    );

    const handleMouseLeave = useCallback(() => {
      setHoveredIdx(-1);
      setShowPreview(false);
    }, []);

    const handleTickClick = useCallback(
      async (item: RailTurnItem) => {
        if (loadingTurnIndex !== null) {
          return;
        }

        // 已载入内存：直接平滑滚动直达
        if (item.isLoaded) {
          if (item.messageIndex >= 0) {
            onJump(item.messageIndex);
          } else if (onJumpToMessageId) {
            onJumpToMessageId(item.userMessageId);
          }
          return;
        }

        // 未载入内存：触发 loadThroughTurn 连续分页加载器（按用户消息 ID 精准锚定）
        if (onLoadThroughTurn) {
          try {
            setLoadingTurnIndex(item.turnIndex);
            await onLoadThroughTurn(item.userMessageId);
            if (onJumpToMessageId) {
              onJumpToMessageId(item.userMessageId);
            }
          } catch (err) {
            console.error('Failed to load through target turn:', err);
          } finally {
            setLoadingTurnIndex(null);
          }
        }
      },
      [loadingTurnIndex, onJump, onJumpToMessageId, onLoadThroughTurn],
    );

    // 键盘轮次跳跃：Alt+↑/↓ 在激活导轨时于相邻轮次间快速移动（复用刻度点击逻辑）
    useEffect(() => {
      if (railItems.length < MIN_TURNS_FOR_RAIL) {
        return;
      }
      const handleKeyDown = (e: KeyboardEvent) => {
        if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) {
          return;
        }
        e.preventDefault();
        const order = railItems.map((i) => i.turnIndex);
        const current = activeViewportTurn ?? railItems[railItems.length - 1].turnIndex;
        const pos = order.indexOf(current);
        const nextPos =
          e.key === 'ArrowUp'
            ? pos < 0
              ? order.length - 1
              : Math.max(0, pos - 1)
            : pos < 0
              ? 0
              : Math.min(order.length - 1, pos + 1);
        const target = railItems[nextPos];
        if (target) {
          void handleTickClick(target);
        }
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }, [railItems, activeViewportTurn, handleTickClick]);

    if (railItems.length < MIN_TURNS_FOR_RAIL) {
      return null;
    }

    const activeHoverItem = hoveredIdx >= 0 ? railItems[hoveredIdx] : null;

    return (
      <div
        ref={barRef}
        className={cn(
          'fixed top-1/2 -translate-y-1/2 z-30 flex flex-col items-center py-4 px-1.5',
          'hidden md:flex select-none',
          'transition-opacity duration-300',
          loading ? 'opacity-60' : 'opacity-100',
          hasGoalPanel ? 'right-3 xl:right-[340px]' : 'right-3',
        )}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        aria-label={t('ariaLabel')}
      >
        {/* 10px 固定步长时间线导轨滚动槽（双端渐变遮罩指示端点） */}
        <div
          className="flex flex-col gap-1.5 items-center max-h-[calc(100vh-8rem)] overflow-y-auto scrollbar-hide py-3 relative"
          style={{
            maskImage:
              'linear-gradient(to bottom, transparent, black 16px, black calc(100% - 16px), transparent)',
            WebkitMaskImage:
              'linear-gradient(to bottom, transparent, black 16px, black calc(100% - 16px), transparent)',
          }}
        >
          {railItems.map((item, idx) => {
            const isLoadingThis = loadingTurnIndex === item.turnIndex;
            const isActiveViewport = activeViewportTurn === item.turnIndex;
            return (
              <button
                key={`${item.turnIndex}-${item.userMessageId}`}
                data-rail-tick
                type="button"
                className="group flex items-center justify-center cursor-pointer p-0 border-0 bg-transparent outline-none focus-visible:ring-1 focus-visible:ring-primary"
                style={{ height: 12 }}
                onClick={() => handleTickClick(item)}
                aria-label={t('jumpToTurn', { index: item.turnIndex })}
              >
                {isLoadingThis ? (
                  <Loader2 className="h-3 w-3 animate-spin text-primary" />
                ) : (
                  <div
                    className={cn(
                      'rounded-full transition-all ease-out',
                      item.isInFlight
                        ? 'h-[5px] bg-primary animate-pulse shadow-sm shadow-primary/50'
                        : item.isLoaded
                          ? 'h-[5px] bg-primary/70 group-hover:bg-primary'
                          : 'h-[3px] bg-muted-foreground/35 group-hover:bg-muted-foreground/75',
                      isActiveViewport && 'bg-primary ring-2 ring-primary/40 ring-offset-1',
                      hoveredIdx >= 0 && Math.abs(idx - hoveredIdx) <= 2 && 'bg-primary',
                    )}
                    style={{
                      width: calculateRailPitchWidth(
                        idx,
                        hoveredIdx,
                        item.isLoaded,
                        isActiveViewport,
                      ),
                      transitionDuration: '150ms',
                    }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* 悬浮轮次大纲精炼预览卡片 */}
        {showPreview && activeHoverItem && (
          <div
            className="absolute right-full mr-3.5 max-w-[280px] w-max p-2.5 rounded-lg
                bg-popover text-popover-foreground text-xs leading-relaxed
                shadow-xl border border-border/80 backdrop-blur-md
                pointer-events-none transition-all duration-150 animate-in fade-in-0 zoom-in-95"
            style={{ top: previewTopRef.current, transform: 'translateY(-50%)' }}
          >
            <div className="flex items-center justify-between gap-3 mb-1.5 pb-1 border-b border-border/40 font-medium">
              <span className="text-primary font-semibold">
                {t('turn', { index: activeHoverItem.turnIndex })}
              </span>
              <span
                className={cn(
                  'px-1.5 py-0.2 rounded text-[10px]',
                  activeHoverItem.isInFlight
                    ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium'
                    : activeHoverItem.isLoaded
                      ? 'bg-primary/15 text-primary'
                      : 'bg-muted text-muted-foreground',
                )}
              >
                {activeHoverItem.isInFlight
                  ? t('inFlight')
                  : activeHoverItem.isLoaded
                    ? t('loaded')
                    : t('unloaded')}
              </span>
            </div>
            <div className="space-y-1">
              <p className="line-clamp-2 text-foreground/90 font-normal">
                <span className="text-muted-foreground mr-1">{t('userPrompt')}:</span>
                {activeHoverItem.promptPreview || '...'}
              </p>
              {activeHoverItem.replyPreview && (
                <p className="line-clamp-2 text-muted-foreground/85 text-[11px]">
                  <span className="text-primary/70 mr-1">{t('assistantReply')}:</span>
                  {activeHoverItem.replyPreview}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    );
  },
);

TurnTimelineRail.displayName = 'TurnTimelineRail';

// ─── 移动端大纲抽屉 ────────────────────────────────────────────────────────

interface MobileTurnOutlineSheetProps {
  messages: Message[];
  turnOutlines?: TurnOutlineItem[];
  onJump: (messageIndex: number) => void;
  onJumpToMessageId?: (messageId: string) => void;
  onLoadThroughTurn?: (userMessageId: string) => Promise<boolean>;
  trigger: React.ReactNode;
}

export const MobileTurnOutlineSheet = memo<MobileTurnOutlineSheetProps>(
  ({ messages, turnOutlines, onJump, onJumpToMessageId, onLoadThroughTurn, trigger }) => {
    const t = useTranslations('chat.turnRail');
    const [open, setOpen] = useState(false);
    const [loadingTurn, setLoadingTurn] = useState<number | null>(null);

    const railItems = useMemo(
      () => normalizeRailItems(messages, turnOutlines),
      [messages, turnOutlines],
    );

    const handleSelect = useCallback(
      async (item: RailTurnItem) => {
        if (item.isLoaded) {
          if (item.messageIndex >= 0) {
            onJump(item.messageIndex);
          } else if (onJumpToMessageId) {
            onJumpToMessageId(item.userMessageId);
          }
          setOpen(false);
          return;
        }

        if (onLoadThroughTurn) {
          try {
            setLoadingTurn(item.turnIndex);
            await onLoadThroughTurn(item.userMessageId);
            if (onJumpToMessageId) {
              onJumpToMessageId(item.userMessageId);
            }
          } catch (e) {
            console.error('Mobile turn load error:', e);
          } finally {
            setLoadingTurn(null);
            setOpen(false);
          }
        }
      },
      [onJump, onJumpToMessageId, onLoadThroughTurn],
    );

    if (railItems.length < MIN_TURNS_FOR_RAIL) {
      return null;
    }

    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>{trigger}</SheetTrigger>
        <SheetContent side="bottom" className="max-h-[65vh] flex flex-col p-4">
          <SheetHeader className="pb-2 border-b border-border/40">
            <SheetTitle className="text-base font-semibold">{t('title')}</SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto mt-2 space-y-2 pr-1">
            {railItems.map((item) => (
              <button
                key={item.turnIndex}
                type="button"
                className="w-full text-left p-2.5 rounded-lg border border-border/50 hover:bg-accent/60
                    transition-all cursor-pointer bg-card/60 flex flex-col gap-1 outline-none"
                onClick={() => handleSelect(item)}
              >
                <div className="flex items-center justify-between text-xs font-medium">
                  <span className="text-primary font-mono">
                    {t('turn', { index: item.turnIndex })}
                  </span>
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded text-[10px]',
                      item.isInFlight
                        ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium'
                        : item.isLoaded
                          ? 'bg-primary/10 text-primary'
                          : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {loadingTurn === item.turnIndex
                      ? t('loading')
                      : item.isInFlight
                        ? t('inFlight')
                        : item.isLoaded
                          ? t('loaded')
                          : t('unloaded')}
                  </span>
                </div>
                <p className="text-xs text-foreground/90 line-clamp-2">
                  {item.promptPreview || '...'}
                </p>
                {item.replyPreview && (
                  <p className="text-[11px] text-muted-foreground line-clamp-1">
                    {item.replyPreview}
                  </p>
                )}
              </button>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    );
  },
);

MobileTurnOutlineSheet.displayName = 'MobileTurnOutlineSheet';