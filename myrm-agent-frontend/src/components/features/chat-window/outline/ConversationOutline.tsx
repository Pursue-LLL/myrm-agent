'use client';

/**
 * [INPUT]
 * - items: OutlineTurnItem[] (POS: 轮次大纲项目列表)
 * - activeViewportTurn: number | null (POS: 视口当前浏览轮次)
 * - onJumpToTurn: (item: OutlineTurnItem) => void (POS: 跳转回调)
 * - isLoading?: boolean (POS: 是否正在流式加载)
 *
 * [OUTPUT]
 * - ConversationOutline: 长对话消息大纲阶梯微缩导航轨组件
 *
 * [POS]
 * 长对话消息大纲阶梯微缩导航轨视图层。
 * 具备阶梯缩放几何学（Staircase Scale）、视口感知罗盘、平滑悬停意图 Tooltip、
 * Alt+↑/↓ 键盘跳跃与长会话紧凑溢出轨。
 * 严格类型：零 `any`。文件行数 < 320 行。零原生 emoji。
 */

import React, { useState, useRef, useCallback, useEffect, memo } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2 } from 'lucide-react';
import { useOutlineGeometry } from './useOutlineGeometry';
import type { ConversationOutlineProps, OutlineTurnItem } from './outlineTypes';

export const ConversationOutline = memo<ConversationOutlineProps>(({
  items,
  activeViewportTurn,
  onJumpToTurn,
  isLoading = false,
  className = '',
}) => {
  const t = useTranslations('chat.turnRail');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipTop, setTooltipTop] = useState<number>(0);
  const trackContainerRef = useRef<HTMLDivElement>(null);

  const geometries = useOutlineGeometry({
    items,
    activeViewportTurn,
    hoveredTurnIndex: hoveredIndex,
  });

  const handleMouseEnterTick = useCallback((turnIndex: number, e: React.MouseEvent<HTMLButtonElement>) => {
    setHoveredIndex(turnIndex);
    if (trackContainerRef.current) {
      const trackRect = trackContainerRef.current.getBoundingClientRect();
      const btnRect = e.currentTarget.getBoundingClientRect();
      const relativeTop = btnRect.top - trackRect.top + btnRect.height / 2;
      setTooltipTop(relativeTop);
    }
  }, []);

  const handleMouseLeaveTrack = useCallback(() => {
    setHoveredIndex(null);
  }, []);

  // 键盘快捷键: Alt+ArrowUp / Alt+ArrowDown 上下轮次跳跃
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) {
        return;
      }
      if (!items || items.length === 0) {
        return;
      }

      e.preventDefault();
      const current = activeViewportTurn ?? items[items.length - 1].turnIndex;
      const step = e.key === 'ArrowUp' ? -1 : 1;
      const targetTurn = current + step;

      const matchedItem = items.find((item) => item.turnIndex === targetTurn);
      if (matchedItem) {
        onJumpToTurn(matchedItem);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [items, activeViewportTurn, onJumpToTurn]);

  if (!items || items.length < 2) {
    return null;
  }

  const activeItem = typeof hoveredIndex === 'number'
    ? items.find((it) => it.turnIndex === hoveredIndex)
    : null;

  return (
    <nav
      aria-label={t('ariaLabel')}
      role="navigation"
      className={`fixed right-3 top-1/2 -translate-y-1/2 z-30 hidden md:flex flex-col items-end select-none pointer-events-auto ${className}`}
    >
      {/* 悬停意图 Tooltip 卡片 */}
      {activeItem && (
        <div
          role="tooltip"
          style={{ top: `${tooltipTop}px` }}
          className="absolute right-10 -translate-y-1/2 w-64 p-3 rounded-2xl bg-card/95 border border-border/80 shadow-2xl backdrop-blur-md text-foreground transition-all duration-160 ease-out z-40 pointer-events-none animate-in fade-in zoom-in-95"
        >
          <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-1.5 mb-2">
            <span className="text-[11px] font-bold text-primary flex items-center gap-1.5">
              <span>{t('turn', { index: activeItem.turnIndex })}</span>
              {activeItem.isInFlight && (
                <span className="inline-flex items-center gap-1 text-[9px] text-amber-500 font-mono">
                  <Loader2 className="w-2.5 h-2.5 animate-spin" />
                  {t('inFlight')}
                </span>
              )}
            </span>
            <span className="text-[10px] font-mono text-muted-foreground">
              {activeItem.isLoaded ? t('loaded') : t('unloaded')}
            </span>
          </div>

          <div className="flex flex-col gap-1.5 text-xs">
            {activeItem.promptPreview && (
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] uppercase font-semibold text-muted-foreground">
                  {t('userPrompt')}
                </span>
                <p className="line-clamp-2 text-foreground/90 font-sans leading-relaxed text-[11px]">
                  {activeItem.promptPreview}
                </p>
              </div>
            )}

            {activeItem.replyPreview && (
              <div className="flex flex-col gap-0.5 pt-1 border-t border-border/40">
                <span className="text-[10px] uppercase font-semibold text-muted-foreground">
                  {t('assistantReply')}
                </span>
                <p className="line-clamp-2 text-muted-foreground font-sans leading-relaxed text-[10px]">
                  {activeItem.replyPreview}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 阶梯微缩轨容器 (长对话紧凑滚动) */}
      <div
        ref={trackContainerRef}
        data-testid="outline-track-container"
        onMouseLeave={handleMouseLeaveTrack}
        className="relative flex flex-col items-end gap-1.5 py-3 px-1.5 rounded-full bg-card/40 border border-border/40 backdrop-blur-xs max-h-[72vh] overflow-y-auto overflow-x-hidden transition-all hover:bg-card/70 hover:border-border/70"
        style={{
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
        }}
      >
        {items.map((item, idx) => {
          const geo = geometries[idx];
          const isCurrent = activeViewportTurn === item.turnIndex;
          const isHovered = hoveredIndex === item.turnIndex;

          const width = geo?.width ?? 12;
          const height = geo?.height ?? 2.5;
          const opacity = geo?.opacity ?? 0.5;

          return (
            <button
              key={item.userMessageId || `turn-${item.turnIndex}`}
              type="button"
              data-outline-tick={item.turnIndex}
              aria-current={isCurrent ? 'location' : undefined}
              aria-label={t('jumpToTurn', { index: item.turnIndex })}
              onClick={() => onJumpToTurn(item)}
              onMouseEnter={(e) => handleMouseEnterTick(item.turnIndex, e)}
              className={`group relative flex items-center justify-end rounded-full transition-all duration-150 ease-out focus:outline-hidden ${
                isCurrent
                  ? 'bg-primary ring-2 ring-primary/40'
                  : item.isInFlight
                  ? 'bg-amber-500 animate-pulse'
                  : item.isLoaded
                  ? 'bg-foreground/50 hover:bg-primary'
                  : 'bg-muted-foreground/30 hover:bg-muted-foreground/60'
              }`}
              style={{
                width: `${isHovered ? width + 6 : width}px`,
                height: `${isHovered ? height + 1 : height}px`,
                opacity: isCurrent ? 1 : isHovered ? 1 : opacity,
              }}
            >
              {/* 当前视口呼吸小圆点 */}
              {isCurrent && (
                <span
                  data-testid="current-viewport-indicator"
                  className="absolute -left-1.5 w-1.5 h-1.5 rounded-full bg-primary animate-ping"
                />
              )}
            </button>
          );
        })}
      </div>

      {isLoading && (
        <div className="mt-1.5 mr-1 flex items-center justify-center">
          <Loader2 className="w-3 h-3 text-muted-foreground animate-spin" />
        </div>
      )}
    </nav>
  );
});

ConversationOutline.displayName = 'ConversationOutline';
