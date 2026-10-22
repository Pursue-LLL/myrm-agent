/**
 * [INPUT]
 * - next/navigation (POS: 清除筛选时改写 URL 查询参数)
 * - next-intl::useTranslations (POS: 国际化翻译)
 *
 * [OUTPUT]
 * - KanbanFilterBanners (default): 看板顶部的「来源会话 / 状态」筛选提示条，带一键清除
 *
 * [POS]
 * 看板主视图由 URL 查询参数带入的筛选条件的提示与清除入口；没有筛选时不渲染任何内容。
 */
'use client';

import { useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { TaskStatus } from '@/services/kanban';

interface KanbanFilterBannersProps {
  sourceChatFilter: string | undefined;
  activeStatusFilter: TaskStatus | undefined;
}

export default function KanbanFilterBanners({ sourceChatFilter, activeStatusFilter }: KanbanFilterBannersProps) {
  const t = useTranslations('kanban');
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const clearSourceChatFilter = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('source_chat');
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }, [pathname, router, searchParams]);

  const clearStatusFilter = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('status');
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }, [pathname, router, searchParams]);

  return (
    <>
      {sourceChatFilter && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
          <span className="text-foreground/80">{t('sourceChatFilterActive', { chatId: sourceChatFilter })}</span>
          <button
            type="button"
            onClick={clearSourceChatFilter}
            className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            {t('clearSourceChatFilter')}
          </button>
        </div>
      )}
      {activeStatusFilter && (
        <div
          className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs"
          data-testid="kanban-status-filter"
        >
          <span className="text-foreground/80">
            {t('statusFilterActive', { status: t(`status.${activeStatusFilter}`, { fallback: activeStatusFilter }) })}
          </span>
          <button
            type="button"
            onClick={clearStatusFilter}
            className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 transition-colors"
          >
            {t('clearStatusFilter')}
          </button>
        </div>
      )}
    </>
  );
}
