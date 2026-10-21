'use client';

/**
 * 溢出标签栏末尾项自动揭示与避让容器组件
 *
 * 对标 penguin-harness #4152，在移动端与桌面端窄窗下自动滚动揭示最后一项目及右侧操作栏。
 */

import React, { useCallback } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTabStripReveal } from './useTabStripReveal';

export interface TabItem {
  id: string;
  label: string;
  badge?: string | number;
  disabled?: boolean;
}

export interface OverflowTabStripContainerProps {
  tabs: TabItem[];
  activeTabId: string;
  onSelectTab: (tabId: string) => void;
  trailingAction?: React.ReactNode;
  className?: string;
  safeMarginPx?: number;
}

export const OverflowTabStripContainer: React.FC<OverflowTabStripContainerProps> = ({
  tabs,
  activeTabId,
  onSelectTab,
  trailingAction,
  className = '',
  safeMarginPx = 16,
}) => {
  const { containerRef, overflowState, revealLastTab } = useTabStripReveal({
    activeTabId,
    safeMarginPx,
  });

  const handleScrollStep = useCallback(
    (direction: 'left' | 'right') => {
      const container = containerRef.current;
      if (!container) {
        return;
      }
      const step = 160;
      const delta = direction === 'left' ? -step : step;
      if (typeof container.scrollBy === 'function') {
        container.scrollBy({
          left: delta,
          behavior: 'smooth',
        });
      } else {
        container.scrollLeft += delta;
      }
    },
    [containerRef],
  );

  return (
    <section
      aria-label="水平滚动标签栏"
      className={`relative flex items-center gap-1.5 w-full overflow-hidden bg-background border-b border-border/70 ${className}`}
      data-testid="overflow-tab-strip-container"
    >
      {/* 左侧溢出阴影与快速滚动按钮 */}
      {overflowState.canScrollLeft && (
        <button
          type="button"
          onClick={() => handleScrollStep('left')}
          className="absolute left-0 z-10 h-full px-1.5 bg-gradient-to-r from-background via-background/90 to-transparent flex items-center justify-center text-muted-foreground hover:text-foreground transition-opacity"
          aria-label="向左滚动标签"
          data-testid="scroll-tabs-left-btn"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      )}

      {/* 滚动容器 */}
      <div
        ref={containerRef}
        role="tablist"
        className="flex items-center gap-1 overflow-x-auto no-scrollbar scroll-smooth py-1.5 px-2 w-full"
        data-testid="tabs-scroll-area"
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTabId;
          const isLast = index === tabs.length - 1;

          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              data-tab-id={tab.id}
              data-is-last-tab={isLast ? 'true' : undefined}
              aria-selected={isActive}
              disabled={tab.disabled}
              onClick={() => {
                onSelectTab(tab.id);
                if (isLast) {
                  revealLastTab();
                }
              }}
              className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                tab.disabled
                  ? 'opacity-40 cursor-not-allowed'
                  : isActive
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/70'
              }`}
              data-testid={`tab-item-${tab.id}`}
            >
              <span className="truncate">{tab.label}</span>
              {tab.badge !== undefined && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                    isActive ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 右侧溢出阴影与快速滚动按钮 */}
      {overflowState.canScrollRight && (
        <button
          type="button"
          onClick={() => handleScrollStep('right')}
          className="absolute right-0 z-10 h-full px-1.5 bg-gradient-to-l from-background via-background/90 to-transparent flex items-center justify-center text-muted-foreground hover:text-foreground transition-opacity"
          aria-label="向右滚动标签"
          data-testid="scroll-tabs-right-btn"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      {/* 右侧操作栏插槽（例如新建标签、设置按钮），末尾自动避让 */}
      {trailingAction && (
        <div className="shrink-0 flex items-center pl-1 pr-2 border-l border-border/40" data-testid="trailing-action-slot">
          {trailingAction}
        </div>
      )}
    </section>
  );
};
