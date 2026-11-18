/**
 * [INPUT]
 * - @/hooks/billing/useQuotaGuard::useQuotaGuard (POS: 发送前的额度校验)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/lib/utils/toast::toast (POS: 统一 toast)
 *
 * [OUTPUT]
 * - useSubmitGate: 返回 `validateAndPrepare`，判定这条提交能否发出（有内容、附件上传完且无失败、额度够）
 *
 * [POS]
 * 聊天输入业务 Hook 的提交门禁：直发、steer、redirect、排队四条提交路径共用，只判定、不发送。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useQuotaGuard } from '@/hooks/billing/useQuotaGuard';
import { toast } from '@/lib/utils/toast';
import type { File as ChatFile } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

export function useSubmitGate(inputMessage: string, files: ChatFile[]) {
  const t = useTranslations('chat');
  const { validateMessageQuota } = useQuotaGuard();

  return useCallback(async (): Promise<boolean> => {
    if (inputMessage.trim().length === 0 && files.length === 0) {
      if (!useChatStore.getState().pendingExplicitSkillActivation) {
        return false;
      }
    }

    // 提交排队安全门禁：等待处于 uploading 状态的媒体就绪 (最长等待 30 秒)
    const currentStoreFiles = useChatStore.getState().files;
    const pendingUploads = currentStoreFiles.filter((f) => f.status === 'uploading');
    if (pendingUploads.length > 0) {
      const start = Date.now();
      while (Date.now() - start < 30000) {
        const checkFiles = useChatStore.getState().files;
        const stillUploading = checkFiles.some((f) => f.status === 'uploading');
        if (!stillUploading) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      const finalFiles = useChatStore.getState().files;
      const failed = finalFiles.some((f) => f.status === 'error');
      if (failed) {
        toast.error(t('uploadFailed'));
        return false;
      }
    }

    const { actionMode } = useChatStore.getState();

    const quota = await validateMessageQuota(inputMessage.trim().length, files.length > 0, actionMode);
    if (!quota.allowed) {
      return false;
    }
    return true;
  }, [inputMessage, files, validateMessageQuota, t]);
}
