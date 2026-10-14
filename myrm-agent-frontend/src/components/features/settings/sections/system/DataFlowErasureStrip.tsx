/**
 * [INPUT]
 * - @/services/conversationPurge::purgeAllConversations, ConversationPurgeBusyError (POS: 会话清空 API 客户端)
 * - @/components/features/app-shell/confirm-dialog::ConfirmDialog
 * - @/store/useChatStore (POS: 侧栏会话列表缓存)
 *
 * [OUTPUT]
 * - DataFlowErasureStrip
 *
 * [POS]
 * DataFlow 面板「清空全部会话」条：二次确认后调用安全清空接口，成功后丢弃侧栏列表缓存并引导新建会话。
 */

'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCheckCircle, IconTrash } from '@/components/features/icons/PremiumIcons';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Button } from '@/components/primitives/button';
import { toast } from '@/lib/utils/toast';
import { ConversationPurgeBusyError, purgeAllConversations } from '@/services/conversationPurge';
import useChatStore from '@/store/useChatStore';

export const DataFlowErasureStrip = memo(() => {
  const t = useTranslations('settings.securityPolicy.dataFlow');
  const tCommon = useTranslations('common');
  const setChatHistoryItems = useChatStore((state) => state.setChatHistoryItems);
  const setChatHistoryPagination = useChatStore((state) => state.setChatHistoryPagination);
  const [clearedCount, setClearedCount] = useState<number | null>(null);

  // 失败只提示、不抛出：ConfirmDialog 对抛出的错误仅写 console，用户看不到原因。
  const handleConfirm = useCallback(async () => {
    try {
      const result = await purgeAllConversations();
      setChatHistoryItems([]);
      setChatHistoryPagination(null);
      setClearedCount(result.purged_chats);
    } catch (error) {
      toast.error(error instanceof ConversationPurgeBusyError ? t('eraseBusy') : t('eraseFailed'));
    }
  }, [setChatHistoryItems, setChatHistoryPagination, t]);

  // 整页跳转而非路由跳转：当前打开的会话已被删除，需要丢弃内存里的消息与流状态。
  const handleStartFresh = useCallback(() => {
    window.location.assign('/');
  }, []);

  return (
    <div className="rounded-xl border border-destructive/25 bg-destructive/5 p-4.5 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-foreground">{t('eraseTitle')}</h4>
        <p className="text-xs text-muted-foreground mt-1">{t('eraseDesc')}</p>
      </div>
      {clearedCount === null ? (
        <ConfirmDialog
          variant="destructive"
          title={t('eraseConfirmTitle')}
          description={t('eraseConfirmDesc')}
          confirmText={t('eraseConfirmAction')}
          cancelText={tCommon('cancel')}
          loadingText={t('erasing')}
          onConfirm={handleConfirm}
          trigger={
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              <IconTrash className="h-3.5 w-3.5 mr-1.5" />
              {t('eraseButton')}
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <output className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <IconCheckCircle className="h-3.5 w-3.5 text-emerald-500" />
            {t('eraseSuccess', { count: clearedCount })}
          </output>
          <Button type="button" size="sm" variant="outline" onClick={handleStartFresh}>
            {t('eraseStartFresh')}
          </Button>
        </div>
      )}
    </div>
  );
});

DataFlowErasureStrip.displayName = 'DataFlowErasureStrip';
