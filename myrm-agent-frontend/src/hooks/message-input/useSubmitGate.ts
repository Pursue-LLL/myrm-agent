/**
 * [INPUT]
 * - @/hooks/billing/useQuotaGuard::useQuotaGuard (POS: 发送前的额度校验)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/lib/utils/toast::toast (POS: 统一 toast)
 *
 * [OUTPUT]
 * - useSubmitGate: 返回 `validateAndPrepare`，判定这条提交能否发出（有内容、附件全部就绪、额度够）
 *
 * [POS]
 * 聊天输入业务 Hook 的提交门禁：直发、steer、redirect、排队四条提交路径共用，只判定、不发送。
 * 附件未就绪（上传失败，或等满 30 秒仍在上传）时拒绝并提示，输入与附件保持原样。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useQuotaGuard } from '@/hooks/billing/useQuotaGuard';
import { toast } from '@/lib/utils/toast';
import type { File as ChatFile } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const UPLOAD_WAIT_MS = 30_000;
const UPLOAD_POLL_MS = 100;

function hasStagedFile(status: NonNullable<ChatFile['status']>): boolean {
  return useChatStore.getState().files.some((f) => f.status === status);
}

export function useSubmitGate(inputMessage: string, files: ChatFile[]) {
  const t = useTranslations('chat');
  const { validateMessageQuota } = useQuotaGuard();

  return useCallback(async (): Promise<boolean> => {
    if (inputMessage.trim().length === 0 && files.length === 0) {
      if (!useChatStore.getState().pendingExplicitSkillActivation) {
        return false;
      }
    }

    // 附件必须全部就绪才能发出：仍在上传的最多等 30 秒，超时或失败都不发。
    // 发出一个没传完或已失败的附件，模型收不到它而用户并不知情；拒绝时输入与附件原样保留，处理后可直接重发。
    const deadline = Date.now() + UPLOAD_WAIT_MS;
    while (hasStagedFile('uploading') && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, UPLOAD_POLL_MS));
    }
    if (hasStagedFile('error')) {
      toast.error(t('uploadFailed'));
      return false;
    }
    if (hasStagedFile('uploading')) {
      toast.warning(t('uploadPending'));
      return false;
    }

    const { actionMode } = useChatStore.getState();

    const quota = await validateMessageQuota(inputMessage.trim().length, files.length > 0, actionMode);
    if (!quota.allowed) {
      return false;
    }
    return true;
  }, [inputMessage, files, validateMessageQuota, t]);
}
