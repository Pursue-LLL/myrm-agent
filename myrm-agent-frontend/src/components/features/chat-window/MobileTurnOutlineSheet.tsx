'use client';

/**
 * [INPUT]
 * - messages: Message[] (POS: 当前内存中已加载的聊天消息列表)
 * - turnOutlines?: TurnOutlineItem[] (POS: 全会话轻量轮次大纲投影)
 * - onJump / onJumpToMessageId / onLoadThroughTurn (POS: 跳转层 `useTurnJump` 使用的定位与分页加载回调)
 * - trigger: React.ReactNode (POS: 抽屉触发按钮插槽)
 *
 * [OUTPUT]
 * - MobileTurnOutlineSheet: 移动端全景大纲抽屉导航组件
 *
 * [POS]
 * 移动端会话大纲抽屉视图层，专司响应式视口下全景轮次浏览与精准跳回。轮次少于 3 时整体不挂载（抽屉开合状态随之清空）；
 * 点选一轮后仅在视口确实送达时才收起抽屉，加载失败则保持打开以便重试。
 */

import React, { useState, useMemo, memo } from 'react';
import type { Message } from '@/store/chat/types';
import type { TurnOutlineItem } from '@/services/chat';
import { cn } from '@/lib/utils/classnameUtils';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { useTranslations } from 'next-intl';
import {
  MIN_TURNS_FOR_RAIL,
  normalizeRailItems,
  railTurnStatus,
  type RailTurnItem,
  type RailTurnStatus,
} from './turnRailModel';
import { useTurnJump, type TurnJumpHandlers } from './useTurnJump';

export interface MobileTurnOutlineSheetProps extends TurnJumpHandlers {
  messages: Message[];
  turnOutlines?: TurnOutlineItem[];
  trigger: React.ReactNode;
}

const BADGE_CLASS: Record<RailTurnStatus, string> = {
  inFlight: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium',
  loaded: 'bg-primary/10 text-primary',
  unloaded: 'bg-muted text-muted-foreground',
};

type OutlineSheetProps = Omit<MobileTurnOutlineSheetProps, 'messages' | 'turnOutlines'> & { items: RailTurnItem[] };

const OutlineSheet = ({ items, trigger, ...handlers }: OutlineSheetProps) => {
  const t = useTranslations('chat.turnRail');
  const [open, setOpen] = useState(false);
  const { loadingTurnIndex, jumpToTurn } = useTurnJump(handlers);

  const handleSelect = async (item: RailTurnItem) => {
    if (await jumpToTurn(item)) {
      setOpen(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="bottom" className="max-h-[65vh] flex flex-col p-4">
        <SheetHeader className="pb-2 border-b border-border/40">
          <SheetTitle className="text-base font-semibold">{t('title')}</SheetTitle>
        </SheetHeader>
        <div className="overflow-y-auto mt-2 space-y-2 pr-1">
          {items.map((item) => {
            const status = railTurnStatus(item);
            return (
              <button
                key={item.turnIndex}
                type="button"
                className="w-full text-left p-2.5 rounded-lg border border-border/50 hover:bg-accent/60 transition-all cursor-pointer bg-card/60 flex flex-col gap-1 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                onClick={() => void handleSelect(item)}
              >
                <div className="flex items-center justify-between text-xs font-medium">
                  <span className="text-primary font-mono">{t('turn', { index: item.turnIndex })}</span>
                  <span className={cn('px-1.5 py-0.5 rounded text-[10px]', BADGE_CLASS[status])}>
                    {loadingTurnIndex === item.turnIndex ? t('loading') : t(status)}
                  </span>
                </div>
                <p className="text-xs text-foreground/90 line-clamp-2">{item.promptPreview || '...'}</p>
                {item.replyPreview && (
                  <p className="text-[11px] text-muted-foreground line-clamp-1">{item.replyPreview}</p>
                )}
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
};

export const MobileTurnOutlineSheet = memo<MobileTurnOutlineSheetProps>(({ messages, turnOutlines, ...rest }) => {
  const items = useMemo(() => normalizeRailItems(messages, turnOutlines), [messages, turnOutlines]);
  return items.length < MIN_TURNS_FOR_RAIL ? null : <OutlineSheet items={items} {...rest} />;
});

MobileTurnOutlineSheet.displayName = 'MobileTurnOutlineSheet';
