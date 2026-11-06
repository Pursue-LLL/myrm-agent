'use client';

/**
 * [INPUT]
 * - ./useChatActions::useChatActions (POS: 单条会话的操作状态)
 * - ./useBatchMode::useBatchMode (POS: 批量选择状态)
 *
 * [OUTPUT]
 * - ChatHistoryDialogs: 会话列表挂载的全部对话框。
 *
 * [POS]
 * 删除确认、批量删除确认、新建自动化、交接、分享、沉淀评测用例；开合与预设全部来自调用方传入的操作状态，本身不持有状态。
 */
import { useTranslations } from 'next-intl';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import CronJobCreateDialog from '@/components/features/cron/CronJobCreateDialog';
import { CaptureEvalCaseDialog } from './CaptureEvalCaseDialog';
import { HandoffDialog } from './HandoffDialog';
import { ShareConversationDialog } from './ShareConversationDialog';
import type { useBatchMode } from './useBatchMode';
import type { useChatActions } from './useChatActions';

interface ChatHistoryDialogsProps {
  actions: ReturnType<typeof useChatActions>;
  batch: ReturnType<typeof useBatchMode>;
}

export function ChatHistoryDialogs({ actions, batch }: ChatHistoryDialogsProps) {
  const t = useTranslations();

  return (
    <>
      <ConfirmDialog
        open={actions.deleteDialogOpen}
        onOpenChange={actions.setDeleteDialogOpen}
        title={t('chat.deleteChat.title')}
        description={t('chat.deleteChat.description')}
        confirmText={t('chat.deleteChat.confirm')}
        cancelText={t('chat.deleteChat.cancel')}
        loadingText={t('chat.deleteChat.deleting')}
        variant="destructive"
        onConfirm={actions.handleDeleteConfirm}
      />

      <ConfirmDialog
        open={batch.batchDeleteDialogOpen}
        onOpenChange={batch.setBatchDeleteDialogOpen}
        title={t('chat.batch.confirmTitle', { count: batch.selectedIds.size })}
        description={t('chat.batch.confirmDesc')}
        confirmText={t('chat.batch.confirmAction')}
        cancelText={t('chat.deleteChat.cancel')}
        loadingText={t('chat.batch.deleting')}
        variant="destructive"
        onConfirm={batch.handleBatchDeleteConfirm}
      />

      <CronJobCreateDialog
        open={actions.automationDialogOpen}
        onOpenChange={actions.setAutomationDialogOpen}
        presetChatId={actions.automationChatId}
        presetChatTitle={actions.automationChatTitle}
      />

      {actions.handoffChatId && (
        <HandoffDialog
          open={actions.handoffDialogOpen}
          onOpenChange={actions.setHandoffDialogOpen}
          chatId={actions.handoffChatId}
          chatTitle={actions.handoffChatTitle}
          currentSource={actions.handoffChatSource}
        />
      )}

      <ShareConversationDialog
        open={actions.shareDialogOpen}
        onOpenChange={actions.setShareDialogOpen}
        shareUrl={actions.shareUrl}
        expiresAt={actions.shareExpiresAt}
        revoked={actions.shareRevoked}
        passwordProtected={actions.sharePasswordProtected}
        loading={actions.shareLoading}
        onCreateLink={actions.handleShareCreate}
        onRevoke={actions.handleShareRevoke}
      />

      <CaptureEvalCaseDialog
        open={actions.captureEvalDialogOpen}
        onOpenChange={actions.setCaptureEvalDialogOpen}
        chatId={actions.captureEvalChatId}
      />
    </>
  );
}
