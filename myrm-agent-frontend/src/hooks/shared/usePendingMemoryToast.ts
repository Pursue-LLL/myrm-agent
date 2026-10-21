/**
 * [INPUT]
 * @/store/memory::useMemoryStore (POS: pending 记忆队列的唯一 store)
 * @/hooks/shared/useToast::toast (POS: toast 封装)
 *
 * [OUTPUT]
 * usePendingMemoryToast: 聊天页挂载时拉取一次待审批队列作为基线，之后队列增长时提示一次
 *
 * [POS]
 * 待审批记忆的聊天内提醒入口。基线只记录不提示，避免刷新页面时对已有积压重复弹出；
 * 订阅 store 变更而非依赖渲染时序，保证首次拉取的结果一定归入基线。
 */

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';

import { toast } from '@/hooks/shared/useToast';
import { useMemoryStore } from '@/store/memory';

const TOAST_DURATION_MS = 4000;

export function usePendingMemoryToast(): void {
  const t = useTranslations('memory');
  const tRef = useRef(t);
  tRef.current = t;

  useEffect(() => {
    const store = useMemoryStore;
    // null = 基线未建立：首次拉取在途时，其结果即基线；首次拉取失败时，
    // 之后第一次成功刷新作为基线，已有积压不会被当作新增提示。
    let baseline: number | null = null;
    let firstFetchSettled = false;

    const unsubscribe = store.subscribe((state, previous) => {
      if (state.pendingCount === previous.pendingCount) {
        return;
      }
      if (baseline === null) {
        if (firstFetchSettled && !state.pendingLoading) {
          baseline = state.pendingCount;
        }
        return;
      }
      if (state.pendingCount > baseline) {
        toast({
          title: tRef.current('pendingToast.title'),
          description: tRef.current('pendingToast.description', { count: state.pendingCount - baseline }),
          duration: TOAST_DURATION_MS,
        });
      }
      baseline = state.pendingCount;
    });

    void store
      .getState()
      .fetchPendingMemories(true)
      .then(() => {
        firstFetchSettled = true;
        const { pendingError, pendingCount } = store.getState();
        baseline = pendingError ? null : pendingCount;
      });

    return unsubscribe;
  }, []);
}
