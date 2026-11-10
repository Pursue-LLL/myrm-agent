/**
 * [INPUT]
 * - handlers: 内存消息索引跳转、消息 ID 定位、按用户消息 ID 连续加载更早轮次
 *
 * [OUTPUT]
 * - useTurnJump: 把视口送到大纲里的某一轮；返回正在加载的轮次序号与 `jumpToTurn`
 *
 * [POS]
 * 时间线导轨与移动端大纲抽屉共用的跳转层。已在内存的轮次直接滚动；更早的轮次先加载，且同一时间只加载一轮，
 * 仅在加载确实到达目标时才移动视口（没到达就不动视口，也不会让聊天停止跟随流式输出），失败时提示用户。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import type { RailTurnItem } from './turnRailModel';

export interface TurnJumpHandlers {
  onJump: (messageIndex: number) => void;
  onJumpToMessageId?: (messageId: string) => void;
  onLoadThroughTurn?: (userMessageId: string) => Promise<boolean>;
}

export function useTurnJump({ onJump, onJumpToMessageId, onLoadThroughTurn }: TurnJumpHandlers) {
  const t = useTranslations('chat.turnRail');
  const [loadingTurnIndex, setLoadingTurnIndex] = useState<number | null>(null);

  /** 视口已送往目标轮次时为 true；另一轮正在加载、无法加载或没有到达目标时为 false。 */
  const jumpToTurn = useCallback(
    async (item: RailTurnItem): Promise<boolean> => {
      if (loadingTurnIndex !== null) {
        return false;
      }
      if (item.isLoaded) {
        onJump(item.messageIndex);
        return true;
      }
      if (!onLoadThroughTurn) {
        return false;
      }

      setLoadingTurnIndex(item.turnIndex);
      try {
        if (await onLoadThroughTurn(item.userMessageId)) {
          onJumpToMessageId?.(item.userMessageId);
          return true;
        }
      } catch (error) {
        console.error('Failed to load through target turn:', error);
      } finally {
        setLoadingTurnIndex(null);
      }
      toast({ title: t('loadFailed'), variant: 'destructive' });
      return false;
    },
    [loadingTurnIndex, onJump, onJumpToMessageId, onLoadThroughTurn, t],
  );

  return { loadingTurnIndex, jumpToTurn };
}
