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
 * DataFlow 面板「清空全部会话」条：二次确认后调用安全清空接口，成功后丢弃侧栏列表缓存并引导新建会话；
 * 仍有未保存改动的沙箱工作区会被服务端保留，结果里单独告知保留数量。
 */

'use client';

import { memo, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconCheckCircle, IconTrash } from '@/components/features/icons/PremiumIcons';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Button } from '@/components/primitives/button';
import { toast } from '@/lib/utils/toast';
import {
  ConversationPurgeBusyError,
  purgeAllConversations,
  type ConversationPurgeResult,
} from '@/services/conversationPurge';
import useChatStore from '@/store/useChatStore';

export const DataFlowErasureStrip = memo(() => {
  const t = useTranslations('settings.securityPolicy.dataFlow');
  const tCommon = useTranslations('common');
  const tChat = useTranslations('chat');
  const setChatHistoryItems = useChatStore((state) => state.setChatHistoryItems);
  const setChatHistoryPagination = useChatStore((state) => state.setChatHistoryPagination);
  const [outcome, setOutcome] = useState<ConversationPurgeResult | null>(null);

  // 失败只提示、不抛出：ConfirmDialog 对抛出的错误仅写 console，用户看不到原因。
  const handleConfirm = useCallback(async () => {
    try {
      const result = await purgeAllConversations();
      setChatHistoryItems([]);
      setChatHistoryPagination(null);
      setOutcome(result);
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
      <div className="flex flex-col sm:flex-row flex-wrap gap-2">
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
        {outcome !== null && (
          <Button type="button" size="sm" variant="outline" onClick={handleStartFresh}>
            {tChat('newChat')}
          </Button>
        )}
      </div>
      {/* 始终挂载：实时区域须先于文字存在，读屏软件才会播报结果。 */}
      <output className="block text-xs font-medium text-foreground empty:hidden">
        {outcome !== null && (
          <>
            <span className="flex items-center gap-1.5">
              <IconCheckCircle className="h-3.5 w-3.5 text-emerald-500" />
              {t('eraseSuccess', { count: outcome.purged_chats })}
            </span>
            {outcome.kept_sandboxes > 0 && (
              <span className="mt-1 block pl-5 font-normal text-muted-foreground">
                {t('eraseKept', { count: outcome.kept_sandboxes })}
              </span>
            )}
          </>
        )}
      </output>
    </div>
  );
});

DataFlowErasureStrip.displayName = 'DataFlowErasureStrip';
