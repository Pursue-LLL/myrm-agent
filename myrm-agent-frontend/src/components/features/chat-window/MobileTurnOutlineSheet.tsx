'use client';

/**
 * [INPUT]
 * - messages: Message[] (POS: 当前内存中已加载的聊天消息列表)
 * - turnOutlines?: TurnOutlineItem[] (POS: 全会话轻量轮次大纲投影)
 * - onJump: (messageIndex: number) => void (POS: 内存消息索引跳转回调)
 * - onJumpToMessageId?: (messageId: string) => void (POS: 消息 ID 精准定位回调)
 * - onLoadThroughTurn?: (userMessageId: string) => Promise<boolean> (POS: 目标轮次连续分页拉取驱动器)
 * - trigger: React.ReactNode (POS: 抽屉触发按钮插槽)
 *
 * [OUTPUT]
 * - MobileTurnOutlineSheet: 移动端全景大纲抽屉导航组件
 *
 * [POS]
 * 移动端会话大纲抽屉视图层。抽离自 TurnTimelineRail，专司响应式视口下全景轮次浏览与精准跳回。
 * 严格类型：零 `any`。文件行数 < 120 行。
 */

import React, { useState, useMemo, useCallback, memo } from 'react';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { useTranslations } from 'next-intl';
import { MIN_TURNS_FOR_RAIL, normalizeRailItems, type RailTurnItem } from './turnRailModel';

export interface MobileTurnOutlineSheetProps {
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

    const railItems = useMemo(() => normalizeRailItems(messages, turnOutlines), [messages, turnOutlines]);

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
                className="w-full text-left p-2.5 rounded-lg border border-border/50 hover:bg-accent/60 transition-all cursor-pointer bg-card/60 flex flex-col gap-1 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                onClick={() => handleSelect(item)}
              >
                <div className="flex items-center justify-between text-xs font-medium">
                  <span className="text-primary font-mono">{t('turn', { index: item.turnIndex })}</span>
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
                <p className="text-xs text-foreground/90 line-clamp-2">{item.promptPreview || '...'}</p>
                {item.replyPreview && (
                  <p className="text-[11px] text-muted-foreground line-clamp-1">{item.replyPreview}</p>
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
