/**
 * [INPUT]
 * - @/hooks/billing/useQuotaGuard::useQuotaGuard (POS: 发送前的额度校验)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - @/lib/utils/toast::toast (POS: 统一 toast)
 *
 * [OUTPUT]
 * - useSubmitGate: 返回 `validateAndPrepare`，判定这条提交能否发出（有内容、附件全部就绪、额度够、仍在提交发起时的会话里）
 *
 * [POS]
 * 聊天输入业务 Hook 的提交门禁：直发、steer、redirect、排队四条提交路径共用，只判定、不发送。
 * 附件未就绪（上传失败，或等满 30 秒仍在上传）时拒绝并提示，输入与附件保持原样。
 * 判定要等上传与额度估算，所以同一时刻只放一次判定在跑，期间的再次提交直接拒绝；跑过一分钟还没结束的判定视为丢失，
 * 不再挡住新的提交，它自己也不再放行。等待期间切到别的会话的提交同样不放行，否则它会发进用户刚打开的那个会话。
 */

import { useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useQuotaGuard } from '@/hooks/billing/useQuotaGuard';
import { toast } from '@/lib/utils/toast';
import type { File as ChatFile } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

const UPLOAD_WAIT_MS = 30_000;
const UPLOAD_POLL_MS = 100;
// 一次判定最长也就是等满上传再加一次估算请求；跑过这么久还没结束的（比如估算请求卡住）视为丢失，不能把输入框永远锁死。
const LOST_CHECK_MS = 60_000;

function hasStagedFile(status: NonNullable<ChatFile['status']>): boolean {
  return useChatStore.getState().files.some((f) => f.status === status);
}

export function useSubmitGate(inputMessage: string, files: ChatFile[]) {
  const t = useTranslations('chat');
  const { validateMessageQuota } = useQuotaGuard();
  // 上传与额度估算（云端是一次网络往返）都要等；此时再按一次发送若也跑完整套判定，两次都会放行，同一条消息就发出两次。
  const runningSince = useRef<number | null>(null);

  return useCallback(async (): Promise<boolean> => {
    const startedAt = Date.now();
    if (runningSince.current !== null && startedAt - runningSince.current < LOST_CHECK_MS) {
      return false;
    }
    if (inputMessage.trim().length === 0 && files.length === 0) {
      if (!useChatStore.getState().pendingExplicitSkillActivation) {
        return false;
      }
    }

    runningSince.current = startedAt;
    const chatIdAtSubmit = useChatStore.getState().chatId;
    // 被后来的判定取代（见 LOST_CHECK_MS）或用户已切到别的会话：这条提交不该再发出。
    const isStale = () => runningSince.current !== startedAt || useChatStore.getState().chatId !== chatIdAtSubmit;
    try {
      // 附件必须全部就绪才能发出：仍在上传的最多等 30 秒，超时或失败都不发。
      // 发出一个没传完或已失败的附件，模型收不到它而用户并不知情；拒绝时输入与附件原样保留，处理后可直接重发。
      // 已失败的附件不会再变好，不必等其余附件传完才告知。
      const deadline = Date.now() + UPLOAD_WAIT_MS;
      while (!hasStagedFile('error') && hasStagedFile('uploading') && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, UPLOAD_POLL_MS));
      }
      // 切了会话时，下面读到的附件也已是那个会话输入框里的，判定不再有意义。
      if (isStale()) {
        return false;
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
      return quota.allowed && !isStale();
    } finally {
      if (runningSince.current === startedAt) {
        runningSince.current = null;
      }
    }
  }, [inputMessage, files, validateMessageQuota, t]);
}
