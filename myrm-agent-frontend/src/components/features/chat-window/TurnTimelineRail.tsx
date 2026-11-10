/**
 * 会话时间线大纲导航导轨组件 (TurnTimelineRail)
 *
 * [INPUT]
 * - messages: Message[] (POS: 当前内存中已加载的聊天消息列表)
 * - turnOutlines?: TurnOutlineItem[] (POS: 全会话轻量轮次大纲投影)
 * - activeViewportTurn?: number | null (POS: 视口当前可见阅读轮次序号，用于阅读罗盘高亮)
 * - onJump / onJumpToMessageId / onLoadThroughTurn (POS: 跳转层 `useTurnJump` 使用的定位与分页加载回调)
 * - loading?: boolean (POS: 是否正在流式生成)
 * - hasGoalPanel?: boolean (POS: 目标面板是否开启，用于右侧定位偏移)
 *
 * [OUTPUT]
 * - TurnTimelineRail: PC 端固定间距 (10px Fixed-Pitch) 垂直时间线导轨（`nav` 地标，含 Alt+↑/↓ 键盘轮次跳跃）
 * - MobileTurnOutlineSheet: 移动端全景大纲抽屉导航（由同名文件再导出）
 *
 * [POS]
 * 长会话全景导航核心组件。轮次少于 3 时整体不挂载（悬浮预览随之清空）；支持已加载/未加载双态刻度、
 * In-Flight 流式轮次动态合成、视口阅读进度实时罗盘联动，悬浮或键盘聚焦刻度时显示轮次预览。
 */

'use client';

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import {
  MIN_TURNS_FOR_RAIL,
  calculateRailPitchWidth,
  normalizeRailItems,
  railTurnStatus,
  type RailTurnItem,
  type RailTurnStatus,
} from './turnRailModel';
import { useTurnJump, type TurnJumpHandlers } from './useTurnJump';
export { MobileTurnOutlineSheet, type MobileTurnOutlineSheetProps } from './MobileTurnOutlineSheet';

interface TurnTimelineRailProps extends TurnJumpHandlers {
  messages: Message[];
  turnOutlines?: TurnOutlineItem[];
  activeViewportTurn?: number | null;
  loading?: boolean;
  hasGoalPanel?: boolean;
}

/** 预览卡片所指的刻度：它的序号，以及它的中心相对导轨顶部的纵向位置。 */
interface RailHover {
  index: number;
  top: number;
}

const TICK_CLASS: Record<RailTurnStatus, string> = {
  inFlight: 'h-[5px] bg-primary animate-pulse shadow-[0_0_5px] shadow-primary/50',
  loaded: 'h-[5px] bg-primary/70 group-hover:bg-primary',
  unloaded: 'h-[3px] bg-muted-foreground/35 group-hover:bg-muted-foreground/75',
};

const BADGE_CLASS: Record<RailTurnStatus, string> = {
  inFlight: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium',
  loaded: 'bg-primary/15 text-primary',
  unloaded: 'bg-muted text-muted-foreground',
};

/** 悬浮轮次大纲精炼预览卡片 */
const RailPreview = ({ item, top }: { item: RailTurnItem; top: number }) => {
  const t = useTranslations('chat.turnRail');
  const status = railTurnStatus(item);
  return (
    <div
      data-testid="turn-rail-preview"
      className="absolute right-full mr-3.5 max-w-[280px] w-max p-2.5 rounded-lg
          bg-popover text-popover-foreground text-xs leading-relaxed
          shadow-xl border border-border/80 backdrop-blur-md
          pointer-events-none transition-all duration-150 animate-in fade-in-0 zoom-in-95"
      style={{ top, transform: 'translateY(-50%)' }}
    >
      <div className="flex items-center justify-between gap-3 mb-1.5 pb-1 border-b border-border/40 font-medium">
        <span className="text-primary font-semibold">{t('turn', { index: item.turnIndex })}</span>
        <span className={cn('px-1.5 py-0.2 rounded text-[10px]', BADGE_CLASS[status])}>{t(status)}</span>
      </div>
      <div className="space-y-1">
        <p className="line-clamp-2 text-foreground/90 font-normal">
          <span className="text-muted-foreground mr-1">{t('userPrompt')}:</span>
          {item.promptPreview || '...'}
        </p>
        {item.replyPreview && (
          <p className="line-clamp-2 text-muted-foreground/85 text-[11px]">
            <span className="text-primary/70 mr-1">{t('assistantReply')}:</span>
            {item.replyPreview}
          </p>
        )}
      </div>
    </div>
  );
};

type RailProps = Omit<TurnTimelineRailProps, 'messages' | 'turnOutlines'> & { items: RailTurnItem[] };

const Rail = ({ items, activeViewportTurn, loading, hasGoalPanel, ...handlers }: RailProps) => {
  const t = useTranslations('chat.turnRail');
  const [hover, setHover] = useState<RailHover | null>(null);
  const barRef = useRef<HTMLElement>(null);
  const { loadingTurnIndex, jumpToTurn } = useTurnJump(handlers);

  /** 预览卡片指向某个刻度；指针停在同一刻度上时沿用原状态，不重复渲染。 */
  const previewTick = useCallback((index: number, tick: HTMLElement) => {
    const bar = barRef.current;
    if (!bar) {
      return;
    }
    const tickRect = tick.getBoundingClientRect();
    const top = tickRect.top + tickRect.height / 2 - bar.getBoundingClientRect().top;
    setHover((current) => (current?.index === index && current.top === top ? current : { index, top }));
  }, []);

  /** 指针在导轨上移动时预览纵向最近的刻度，所以刻度之间的缝隙不会让预览闪灭。 */
  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const ticks = barRef.current?.querySelectorAll<HTMLElement>('[data-rail-tick]');
      if (!ticks?.length) {
        return;
      }
      let closest = 0;
      let closestDist = Infinity;
      ticks.forEach((tick, i) => {
        const r = tick.getBoundingClientRect();
        const dist = Math.abs(e.clientY - (r.top + r.height / 2));
        if (dist < closestDist) {
          closestDist = dist;
          closest = i;
        }
      });
      previewTick(closest, ticks[closest]);
    },
    [previewTick],
  );

  /** 焦点移出整条导轨才收起预览；在刻度之间移动焦点时预览跟着走。 */
  const handleBlur = useCallback((e: React.FocusEvent<HTMLElement>) => {
    const next = e.relatedTarget;
    if (!(next instanceof Node && e.currentTarget.contains(next))) {
      setHover(null);
    }
  }, []);

  // 键盘轮次跳跃：Alt+↑/↓ 从视口正在阅读的轮次（没有则从最后一轮）走到相邻轮次
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) {
        return;
      }
      e.preventDefault();
      const last = items.length - 1;
      const current = items.findIndex((item) => item.turnIndex === (activeViewportTurn ?? items[last].turnIndex));
      const step = e.key === 'ArrowUp' ? -1 : 1;
      const next = current < 0 ? (step < 0 ? last : 0) : Math.min(last, Math.max(0, current + step));
      void jumpToTurn(items[next]);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [items, activeViewportTurn, jumpToTurn]);

  const hovered = hover ? items[hover.index] : undefined;
  const hoverIndex = hover?.index ?? -1;

  return (
    <nav
      ref={barRef}
      data-testid="turn-timeline-rail"
      className={cn(
        'fixed top-1/2 -translate-y-1/2 z-30',
        'hidden md:flex select-none',
        'transition-opacity duration-300',
        loading ? 'opacity-60' : 'opacity-100',
        hasGoalPanel ? 'right-3 xl:right-[340px]' : 'right-3',
      )}
      aria-label={t('ariaLabel')}
    >
      {/* `nav` 只是地标；指针与焦点的监听挂在它里面的这一层 */}
      <div
        className="flex flex-col items-center py-4 px-1.5"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
        onBlur={handleBlur}
      >
        {/* 10px 固定步长时间线导轨滚动槽（双端渐变遮罩指示端点） */}
        <div
          className="flex flex-col gap-1.5 items-center max-h-[calc(100vh-8rem)] overflow-y-auto scrollbar-hide py-3 relative"
          style={{
            maskImage: 'linear-gradient(to bottom, transparent, black 16px, black calc(100% - 16px), transparent)',
            WebkitMaskImage:
              'linear-gradient(to bottom, transparent, black 16px, black calc(100% - 16px), transparent)',
          }}
        >
          {items.map((item, idx) => {
            const isActiveViewport = activeViewportTurn === item.turnIndex;
            return (
              <button
                key={`${item.turnIndex}-${item.userMessageId}`}
                data-rail-tick
                type="button"
                className="group flex items-center justify-center cursor-pointer p-0 border-0 bg-transparent outline-none focus-visible:ring-1 focus-visible:ring-primary"
                style={{ height: 12 }}
                onClick={() => void jumpToTurn(item)}
                onMouseEnter={(e) => previewTick(idx, e.currentTarget)}
                onFocus={(e) => previewTick(idx, e.currentTarget)}
                aria-label={t('jumpToTurn', { index: item.turnIndex })}
                aria-current={isActiveViewport ? 'location' : undefined}
              >
                {loadingTurnIndex === item.turnIndex ? (
                  <Loader2 className="h-3 w-3 animate-spin text-primary" />
                ) : (
                  <div
                    className={cn(
                      'rounded-full transition-all ease-out',
                      TICK_CLASS[railTurnStatus(item)],
                      isActiveViewport && 'bg-primary ring-2 ring-primary/40 ring-offset-1',
                      hoverIndex >= 0 && Math.abs(idx - hoverIndex) <= 2 && 'bg-primary',
                    )}
                    style={{
                      width: calculateRailPitchWidth(idx, hoverIndex, item.isLoaded, isActiveViewport),
                      transitionDuration: '150ms',
                    }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {hover && hovered && <RailPreview item={hovered} top={hover.top} />}
    </nav>
  );
};

export const TurnTimelineRail = memo<TurnTimelineRailProps>(({ messages, turnOutlines, ...rest }) => {
  const items = useMemo(() => normalizeRailItems(messages, turnOutlines), [messages, turnOutlines]);
  return items.length < MIN_TURNS_FOR_RAIL ? null : <Rail items={items} {...rest} />;
});

TurnTimelineRail.displayName = 'TurnTimelineRail';
