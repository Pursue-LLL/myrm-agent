/**
 * [INPUT]
 * - useBrowserTakeoverStore (POS: 浏览器 HITL takeover 请求状态)
 * - useChatStore (POS: 当前会话消息发送与流式状态)
 * - @/lib/api::fetchWithTimeout (POS: 带超时的 REST 客户端)
 *
 * [OUTPUT]
 * useBrowserTakeoverActions: Complete/Skip 操作与 managed 模式 VNC resume 同步
 *
 * [POS]
 * 浏览器 takeover 用户操作的共享 Hook。Extension 横幅与 VNC 面板共用，避免重复逻辑。
 */

'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import useBrowserTakeoverStore, {
  type BrowserTakeoverUiMode,
} from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';

async function resumeVncSession(uiMode: BrowserTakeoverUiMode): Promise<{ learned: boolean } | null> {
  if (uiMode !== 'managed') {
    return null;
  }
  const { fetchWithTimeout } = await import('@/lib/api');
  const resumeRes = await fetchWithTimeout('/webui/vnc/resume', { method: 'POST' });
  if (!resumeRes.ok) {
    throw new Error(`VNC resume failed with status ${resumeRes.status}`);
  }
  return (await resumeRes.json()) as { learned: boolean };
}

export function useBrowserTakeoverActions() {
  const t = useTranslations('billing.vnc');
  const messageId = useBrowserTakeoverStore((s) => s.messageId);
  const completeTakeover = useBrowserTakeoverStore((s) => s.completeTakeover);

  const handleTakeoverComplete = useCallback(async () => {
    const snapshot = {
      messageId: useBrowserTakeoverStore.getState().messageId,
      uiMode: useBrowserTakeoverStore.getState().uiMode,
      reason: useBrowserTakeoverStore.getState().reason,
      autoDetectCompletion: useBrowserTakeoverStore.getState().autoDetectCompletion,
      screenshotBase64: useBrowserTakeoverStore.getState().screenshotBase64,
      url: useBrowserTakeoverStore.getState().url,
    };
    completeTakeover();
    if (!snapshot.messageId) {
      return;
    }
    try {
      const resumeData = await resumeVncSession(snapshot.uiMode);
      await useChatStore
        .getState()
        .sendMessage('', snapshot.messageId, undefined, { action: 'completed', message: '' });
      if (resumeData?.learned) {
        toast.success(t('takeoverLearned'), { duration: 3000 });
      }
    } catch (error) {
      console.error('[TAKEOVER] Resume failed:', error);
      useBrowserTakeoverStore.getState().requestTakeover({
        reason: snapshot.reason,
        messageId: snapshot.messageId,
        ui_mode: snapshot.uiMode,
        auto_detect_completion: snapshot.autoDetectCompletion,
        screenshot_base64: snapshot.screenshotBase64,
        url: snapshot.url,
      });
      toast.error(t('takeoverResumeFailed'));
    }
  }, [messageId, completeTakeover, t]);

  const handleTakeoverSkip = useCallback(async () => {
    const snapshot = {
      messageId: useBrowserTakeoverStore.getState().messageId,
      uiMode: useBrowserTakeoverStore.getState().uiMode,
      reason: useBrowserTakeoverStore.getState().reason,
      autoDetectCompletion: useBrowserTakeoverStore.getState().autoDetectCompletion,
      screenshotBase64: useBrowserTakeoverStore.getState().screenshotBase64,
      url: useBrowserTakeoverStore.getState().url,
    };
    completeTakeover();
    if (!snapshot.messageId) {
      return;
    }
    try {
      await resumeVncSession(snapshot.uiMode);
      await useChatStore
        .getState()
        .sendMessage('', snapshot.messageId, undefined, { action: 'skipped', message: '' });
    } catch (error) {
      console.error('[TAKEOVER] Skip failed:', error);
      useBrowserTakeoverStore.getState().requestTakeover({
        reason: snapshot.reason,
        messageId: snapshot.messageId,
        ui_mode: snapshot.uiMode,
        auto_detect_completion: snapshot.autoDetectCompletion,
        screenshot_base64: snapshot.screenshotBase64,
        url: snapshot.url,
      });
      toast.error(t('takeoverResumeFailed'));
    }
  }, [messageId, completeTakeover, t]);

  return { handleTakeoverComplete, handleTakeoverSkip };
}
