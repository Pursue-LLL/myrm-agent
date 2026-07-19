'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useChatStore from '@/store/useChatStore';

async function resumeVncSessionIfManaged(): Promise<{ learned: boolean } | null> {
  if (useBrowserTakeoverStore.getState().uiMode !== 'managed') {
    return null;
  }
  const { fetchWithTimeout } = await import('@/lib/api');
  const resumeRes = await fetchWithTimeout('/webui/vnc/resume', { method: 'POST' });
  if (!resumeRes.ok) {
    return null;
  }
  return (await resumeRes.json()) as { learned: boolean };
}

export function useBrowserTakeoverActions() {
  const t = useTranslations('billing.vnc');
  const messageId = useBrowserTakeoverStore((s) => s.messageId);
  const completeTakeover = useBrowserTakeoverStore((s) => s.completeTakeover);

  const handleTakeoverComplete = useCallback(async () => {
    const storedMessageId = messageId;
    const prevReason = useBrowserTakeoverStore.getState().reason;
    const prevPayload = {
      reason: prevReason,
      messageId: storedMessageId,
      ui_mode: useBrowserTakeoverStore.getState().uiMode,
      auto_detect_completion: useBrowserTakeoverStore.getState().autoDetectCompletion,
      screenshot_base64: useBrowserTakeoverStore.getState().screenshotBase64,
      url: useBrowserTakeoverStore.getState().url,
    };
    completeTakeover();
    if (!storedMessageId) {
      return;
    }
    try {
      const resumeData = await resumeVncSessionIfManaged();
      await useChatStore.getState().sendMessage('', storedMessageId, undefined, { action: 'completed', message: '' });
      if (resumeData?.learned) {
        toast.success(t('takeoverLearned'), { duration: 3000 });
      }
    } catch (error) {
      console.error('[TAKEOVER] Resume failed:', error);
      useBrowserTakeoverStore.getState().requestTakeover(prevPayload);
      toast.error(t('takeoverResumeFailed'));
    }
  }, [messageId, completeTakeover, t]);

  const handleTakeoverSkip = useCallback(async () => {
    const storedMessageId = messageId;
    completeTakeover();
    if (!storedMessageId) {
      return;
    }
    try {
      await resumeVncSessionIfManaged();
      await useChatStore.getState().sendMessage('', storedMessageId, undefined, { action: 'skipped', message: '' });
    } catch (error) {
      console.error('[TAKEOVER] Skip failed:', error);
      toast.error(t('takeoverResumeFailed'));
    }
  }, [messageId, completeTakeover, t]);

  return { handleTakeoverComplete, handleTakeoverSkip };
}
